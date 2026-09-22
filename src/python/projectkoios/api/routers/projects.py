from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from projectkoios.api.project_models import PublicProjectCatalog


class PublicProjectProvider(Protocol):
    def list_projects(self) -> PublicProjectCatalog: ...


def create_projects_router(projects: PublicProjectProvider) -> APIRouter:
    router = APIRouter(prefix="/api/projects", tags=["projects"])

    @router.get("", response_model=PublicProjectCatalog)
    def list_projects() -> PublicProjectCatalog:
        return projects.list_projects()

    return router
