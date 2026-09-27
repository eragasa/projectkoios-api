from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, HTTPException, status
from projectkoios.api.course_models import PublicCourseCatalog
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.provider_errors import ProviderUnavailable


class PublicCourseProvider(Protocol):
    def list_courses(self) -> PublicCourseCatalog: ...


def create_courses_router(courses: PublicCourseProvider) -> APIRouter:
    router = APIRouter(prefix="/api/courses", tags=["courses"])

    @router.get(
        "",
        response_model=PublicCourseCatalog,
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ApiErrorResponse,
                "description": "The public course projection is unavailable.",
            }
        },
    )
    def list_courses() -> PublicCourseCatalog:
        try:
            return courses.list_courses()
        except ProviderUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="public course provider is unavailable",
            ) from error

    return router
