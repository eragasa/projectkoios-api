import asyncio
from dataclasses import dataclass

import httpx2
from fastapi import FastAPI
from projectkoios.api.publication_models import PublicationCatalog
from projectkoios.api.routers.publications import create_publications_router


@dataclass(frozen=True)
class StubPublicationProvider:
    catalog: PublicationCatalog

    def list_publications(self) -> PublicationCatalog:
        return self.catalog


def test__list_publications__returns_public_catalog() -> None:
    application = FastAPI()
    application.include_router(
        create_publications_router(
            StubPublicationProvider(PublicationCatalog())
        )
    )

    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=application)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/api/publications")

    response = asyncio.run(send())

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1",
        "publications": [],
    }
