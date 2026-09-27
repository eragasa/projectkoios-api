from __future__ import annotations

from typing import Annotated, Any, Protocol

from fastapi import APIRouter, HTTPException, Query, status
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.organizer_models import (
    LifeDomain,
    OrganizerControlMode,
    OrganizerControlRequest,
    OrganizerProposalListResponse,
    OrganizerStatusResponse,
)
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    validated_provider_projection,
)
from projectkoios.api.provider_errors import ProviderUnavailable

_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": "The organizer owner adapter failed unexpectedly.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ApiErrorResponse,
        "description": (
            "The organizer owner adapter returned an invalid projection."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorResponse,
        "description": "No organizer owner adapter is available.",
    },
}


class OrganizerProvider(Protocol):
    """Narrow port implemented by the organizer domain owner."""

    def read_status(self) -> OrganizerStatusResponse: ...

    def set_control(
        self, mode: OrganizerControlMode
    ) -> OrganizerStatusResponse: ...

    def list_proposals(
        self,
        *,
        life_domain: LifeDomain,
        limit: int,
    ) -> OrganizerProposalListResponse: ...


def create_organizer_router(
    provider: OrganizerProvider | None,
) -> APIRouter:
    router = APIRouter(prefix="/organizer", tags=["organizer"])

    @router.get(
        "/status",
        response_model=OrganizerStatusResponse,
        responses=_PROVIDER_RESPONSES,
    )
    def read_status() -> OrganizerStatusResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                owner.read_status,
                OrganizerStatusResponse,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    @router.put(
        "/control",
        response_model=OrganizerStatusResponse,
        responses=_PROVIDER_RESPONSES,
    )
    def update_control(
        request: OrganizerControlRequest,
    ) -> OrganizerStatusResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                lambda: owner.set_control(request.mode),
                OrganizerStatusResponse,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    @router.get(
        "/proposals",
        response_model=OrganizerProposalListResponse,
        responses=_PROVIDER_RESPONSES,
    )
    def read_proposals(
        life_domain: Annotated[
            LifeDomain,
            Query(),
        ] = LifeDomain.TEACHING,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> OrganizerProposalListResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                lambda: owner.list_proposals(
                    life_domain=life_domain,
                    limit=limit,
                ),
                OrganizerProposalListResponse,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    return router


def _require_provider(
    provider: OrganizerProvider | None,
) -> OrganizerProvider:
    if provider is None:
        raise _provider_unavailable()
    return provider


def _provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="organizer provider is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="organizer provider returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="organizer provider failed unexpectedly",
    )
