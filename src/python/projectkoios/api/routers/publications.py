from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from projectkoios.api.publication_models import PublicationCatalog


class PublicationProvider(Protocol):
    def list_publications(self) -> PublicationCatalog: ...


def create_publications_router(
    publications: PublicationProvider,
) -> APIRouter:
    router = APIRouter(prefix="/api/publications", tags=["publications"])

    @router.get("", response_model=PublicationCatalog)
    def list_publications() -> PublicationCatalog:
        return publications.list_publications()

    return router
