from __future__ import annotations

from typing import Annotated, Protocol

from fastapi import APIRouter, HTTPException, Query, status
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.organizer_models import (
    LifeDomain,
    OrganizerControlMode,
    OrganizerControlRequest,
    OrganizerProposalListResponse,
    OrganizerStatusResponse,
)
from projectkoios.api.provider_errors import ProviderUnavailable


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
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ApiErrorResponse,
                "description": "No organizer owner adapter is available.",
            }
        },
    )
    def read_status() -> OrganizerStatusResponse:
        owner = _require_provider(provider)
        try:
            return owner.read_status()
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error

    @router.put(
        "/control",
        response_model=OrganizerStatusResponse,
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ApiErrorResponse,
                "description": "No organizer owner adapter is available.",
            }
        },
    )
    def update_control(
        request: OrganizerControlRequest,
    ) -> OrganizerStatusResponse:
        owner = _require_provider(provider)
        try:
            return owner.set_control(request.mode)
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error

    @router.get(
        "/proposals",
        response_model=OrganizerProposalListResponse,
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ApiErrorResponse,
                "description": "No organizer owner adapter is available.",
            }
        },
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
            return owner.list_proposals(
                life_domain=life_domain,
                limit=limit,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error

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
