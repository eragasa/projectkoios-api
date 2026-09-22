import asyncio

import httpx2
from fastapi import FastAPI
from projectkoios.api.course_models import PublicCourseCatalog
from projectkoios.api.routers.courses import create_courses_router


class StubPublicCourseProvider:
    def list_courses(self) -> PublicCourseCatalog:
        return PublicCourseCatalog(schema_version="1")


def test__list_courses__returns_public_safe_catalog() -> None:
    application = FastAPI()
    application.include_router(
        create_courses_router(StubPublicCourseProvider())
    )

    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=application)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/api/courses")

    response = asyncio.run(send())

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1",
        "reviewed_on": None,
        "source": None,
        "publication_boundary": [],
        "institutions": [],
        "unresolved_collections": [],
    }
