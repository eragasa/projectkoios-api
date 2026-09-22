import asyncio

import httpx2
from fastapi import FastAPI
from projectkoios.api.project_models import PublicProjectCatalog
from projectkoios.api.routers.projects import create_projects_router


class StubPublicProjectProvider:
    def list_projects(self) -> PublicProjectCatalog:
        return PublicProjectCatalog(schema_version="1", projects=())


def test__list_projects__returns_public_catalog() -> None:
    application = FastAPI()
    application.include_router(
        create_projects_router(StubPublicProjectProvider())
    )

    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=application)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/api/projects")

    response = asyncio.run(send())

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1",
        "projects": [],
    }
