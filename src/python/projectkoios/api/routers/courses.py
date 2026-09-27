from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, status
from projectkoios.api.course_models import PublicCourseCatalog
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    validated_provider_projection,
)
from projectkoios.api.provider_errors import ProviderUnavailable

_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": "The public course provider failed unexpectedly.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ApiErrorResponse,
        "description": (
            "The public course provider returned an invalid projection."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorResponse,
        "description": "The public course projection is unavailable.",
    },
}


class PublicCourseProvider(Protocol):
    def list_courses(self) -> PublicCourseCatalog: ...


def create_courses_router(courses: PublicCourseProvider) -> APIRouter:
    router = APIRouter(prefix="/api/courses", tags=["courses"])

    @router.get(
        "",
        response_model=PublicCourseCatalog,
        responses=_PROVIDER_RESPONSES,
    )
    def list_courses() -> PublicCourseCatalog:
        try:
            return validated_provider_projection(
                courses.list_courses,
                PublicCourseCatalog,
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
        detail="public course provider is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="public course provider returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="public course provider failed unexpectedly",
    )
