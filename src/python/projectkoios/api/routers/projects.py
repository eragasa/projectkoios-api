from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, status
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.project_models import PublicProjectCatalog
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    validated_provider_projection,
)
from projectkoios.api.provider_errors import ProviderUnavailable

_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": "The public project provider failed unexpectedly.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ApiErrorResponse,
        "description": (
            "The public project provider returned an invalid projection."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorResponse,
        "description": "The public project projection is unavailable.",
    },
}


class PublicProjectProvider(Protocol):
    def list_projects(self) -> PublicProjectCatalog: ...


def create_projects_router(projects: PublicProjectProvider) -> APIRouter:
    router = APIRouter(prefix="/api/projects", tags=["projects"])

    @router.get(
        "",
        response_model=PublicProjectCatalog,
        responses=_PROVIDER_RESPONSES,
    )
    def list_projects() -> PublicProjectCatalog:
        try:
            return validated_provider_projection(
                projects.list_projects,
                PublicProjectCatalog,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    return router


def _provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="public project provider is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="public project provider returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="public project provider failed unexpectedly",
    )
