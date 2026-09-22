from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from projectkoios.api.course_models import PublicCourseCatalog


class PublicCourseProvider(Protocol):
    def list_courses(self) -> PublicCourseCatalog: ...


def create_courses_router(courses: PublicCourseProvider) -> APIRouter:
    router = APIRouter(prefix="/api/courses", tags=["courses"])

    @router.get("", response_model=PublicCourseCatalog)
    def list_courses() -> PublicCourseCatalog:
        return courses.list_courses()

    return router
