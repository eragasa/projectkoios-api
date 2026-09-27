from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.course_models import PublicCourseCatalog
from projectkoios.api.project_models import PublicProjectCatalog
from projectkoios.api.provider_errors import ProviderUnavailable
from projectkoios.api.routers.courses import create_courses_router
from projectkoios.api.routers.projects import create_projects_router


class _CourseFixture:
    def list_courses(self) -> PublicCourseCatalog:
        return PublicCourseCatalog()


class _ProjectFixture:
    def list_projects(self) -> PublicProjectCatalog:
        return PublicProjectCatalog()


class _UnavailableCourse:
    def list_courses(self) -> PublicCourseCatalog:
        raise ProviderUnavailable


class _UnavailableProject:
    def list_projects(self) -> PublicProjectCatalog:
        raise ProviderUnavailable


def test__public_contract_routers__return_injected_projections() -> None:
    app = FastAPI()
    app.include_router(create_courses_router(_CourseFixture()))
    app.include_router(create_projects_router(_ProjectFixture()))
    client = TestClient(app)

    courses = client.get("/api/courses")
    projects = client.get("/api/projects")

    assert courses.status_code == 200
    assert courses.json() == {
        "schema_version": "1",
        "reviewed_on": None,
        "source": None,
        "publication_boundary": [],
        "institutions": [],
        "unresolved_collections": [],
    }
    assert projects.status_code == 200
    assert projects.json() == {"schema_version": "1", "projects": []}


def test__public_contract_routers__map_provider_unavailability() -> None:
    app = FastAPI()
    app.include_router(create_courses_router(_UnavailableCourse()))
    app.include_router(create_projects_router(_UnavailableProject()))
    client = TestClient(app)

    courses = client.get("/api/courses")
    projects = client.get("/api/projects")

    assert courses.status_code == 503
    assert courses.json() == {"detail": "public course provider is unavailable"}
    assert projects.status_code == 503
    assert projects.json() == {
        "detail": "public project provider is unavailable"
    }
