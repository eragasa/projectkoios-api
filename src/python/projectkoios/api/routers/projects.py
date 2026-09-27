from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, HTTPException, status
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.project_models import PublicProjectCatalog
from projectkoios.api.provider_errors import ProviderUnavailable


class PublicProjectProvider(Protocol):
    def list_projects(self) -> PublicProjectCatalog: ...


def create_projects_router(projects: PublicProjectProvider) -> APIRouter:
    router = APIRouter(prefix="/api/projects", tags=["projects"])

    @router.get(
        "",
        response_model=PublicProjectCatalog,
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ApiErrorResponse,
                "description": "The public project projection is unavailable.",
            }
        },
    )
    def list_projects() -> PublicProjectCatalog:
        try:
            return projects.list_projects()
        except ProviderUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="public project provider is unavailable",
            ) from error

    return router
