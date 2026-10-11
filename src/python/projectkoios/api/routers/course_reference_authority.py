from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Response, status
from fastapi.responses import JSONResponse
from projectkoios.api.course_reference_authority import (
    CourseReferenceAuthorityFailure,
    CourseReferenceAuthorityProvider,
)
from projectkoios.api.course_reference_authority_models import (
    AssetDecisionPreviewRequest,
    AssetDecisionPreviewResponse,
    AssetDecisionRequest,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceFailureResponse,
    CourseReferenceQueueResponse,
    IdentityDecisionPreviewRequest,
    IdentityDecisionPreviewResponse,
    IdentityDecisionRequest,
)

CourseIdPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$",
    ),
]
ItemIdPath = Annotated[
    str,
    Path(
        min_length=73,
        max_length=512,
        pattern=r"^[a-z][a-z0-9.-]*:sha256:[0-9a-f]{64}$",
    ),
]

_FAILURE_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": CourseReferenceFailureResponse,
        "description": "The course or exact Courses-owned item is absent.",
    },
    status.HTTP_409_CONFLICT: {
        "model": CourseReferenceFailureResponse,
        "description": (
            "The requested evidence, revision, target, disposition, or append "
            "position is stale or invalid."
        ),
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": CourseReferenceFailureResponse,
        "description": "The owner returned malformed authority evidence.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": CourseReferenceFailureResponse,
        "description": "The owner authority service is unavailable.",
    },
}


def create_course_reference_authority_router(
    provider: CourseReferenceAuthorityProvider,
) -> APIRouter:
    router = APIRouter(tags=["course-reference-authority"])

    @router.get(
        "/courses/{course_id}/references",
        response_model=CourseReferenceQueueResponse,
        responses=_FAILURE_RESPONSES,
    )
    def queue(
        course_id: CourseIdPath,
    ) -> CourseReferenceQueueResponse | Response:
        try:
            return provider.queue(str(course_id))
        except CourseReferenceAuthorityFailure as error:
            return _failure(error.code)

    @router.post(
        "/courses/{course_id}/references/{item_id}/decision-preview",
        response_model=IdentityDecisionPreviewResponse,
        responses=_FAILURE_RESPONSES,
    )
    def preview_identity(
        course_id: CourseIdPath,
        item_id: ItemIdPath,
        request: IdentityDecisionPreviewRequest,
    ) -> IdentityDecisionPreviewResponse | Response:
        try:
            return provider.preview_identity(
                str(course_id),
                str(item_id),
                request,
            )
        except CourseReferenceAuthorityFailure as error:
            return _failure(error.code)

    @router.post(
        "/courses/{course_id}/references/{item_id}/asset-decision-preview",
        response_model=AssetDecisionPreviewResponse,
        responses=_FAILURE_RESPONSES,
    )
    def preview_asset(
        course_id: CourseIdPath,
        item_id: ItemIdPath,
        request: AssetDecisionPreviewRequest,
    ) -> AssetDecisionPreviewResponse | Response:
        try:
            return provider.preview_asset(
                str(course_id),
                str(item_id),
                request,
            )
        except CourseReferenceAuthorityFailure as error:
            return _failure(error.code)

    @router.put(
        "/courses/{course_id}/references/{item_id}/decision",
        response_model=CourseReferenceDecisionReceiptResponse,
        responses=_FAILURE_RESPONSES,
    )
    def decide_identity(
        course_id: CourseIdPath,
        item_id: ItemIdPath,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse | Response:
        try:
            return provider.decide_identity(
                str(course_id),
                str(item_id),
                request,
            )
        except CourseReferenceAuthorityFailure as error:
            return _failure(error.code)

    @router.put(
        "/courses/{course_id}/references/{item_id}/asset-decision",
        response_model=CourseReferenceDecisionReceiptResponse,
        responses=_FAILURE_RESPONSES,
    )
    def decide_asset(
        course_id: CourseIdPath,
        item_id: ItemIdPath,
        request: AssetDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse | Response:
        try:
            return provider.decide_asset(
                str(course_id),
                str(item_id),
                request,
            )
        except CourseReferenceAuthorityFailure as error:
            return _failure(error.code)

    return router


def _failure(code: CourseReferenceFailureCode) -> JSONResponse:
    status_code = {
        CourseReferenceFailureCode.COURSE_NOT_FOUND: (
            status.HTTP_404_NOT_FOUND
        ),
        CourseReferenceFailureCode.ITEM_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        CourseReferenceFailureCode.EVIDENCE_STALE: status.HTTP_409_CONFLICT,
        CourseReferenceFailureCode.REVISION_STALE: status.HTTP_409_CONFLICT,
        CourseReferenceFailureCode.TARGET_STALE: status.HTTP_409_CONFLICT,
        CourseReferenceFailureCode.CONCURRENT_DECISION: (
            status.HTTP_409_CONFLICT
        ),
        CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT: (
            status.HTTP_409_CONFLICT
        ),
        CourseReferenceFailureCode.INVALID_DISPOSITION: (
            status.HTTP_409_CONFLICT
        ),
        CourseReferenceFailureCode.OWNER_MALFORMED: (
            status.HTTP_502_BAD_GATEWAY
        ),
        CourseReferenceFailureCode.OWNER_UNAVAILABLE: (
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
    }[code]
    detail = {
        CourseReferenceFailureCode.COURSE_NOT_FOUND: (
            "course reference authority was not found"
        ),
        CourseReferenceFailureCode.ITEM_NOT_FOUND: (
            "course reference item was not found"
        ),
        CourseReferenceFailureCode.EVIDENCE_STALE: (
            "course reference evidence is stale"
        ),
        CourseReferenceFailureCode.REVISION_STALE: (
            "course reference revision is stale"
        ),
        CourseReferenceFailureCode.TARGET_STALE: (
            "course reference target is stale"
        ),
        CourseReferenceFailureCode.CONCURRENT_DECISION: (
            "a different authority decision won concurrently"
        ),
        CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT: (
            "idempotency key was already used for another decision"
        ),
        CourseReferenceFailureCode.INVALID_DISPOSITION: (
            "course reference disposition is invalid"
        ),
        CourseReferenceFailureCode.OWNER_MALFORMED: (
            "reference owner returned malformed authority evidence"
        ),
        CourseReferenceFailureCode.OWNER_UNAVAILABLE: (
            "reference owner is unavailable"
        ),
    }[code]
    return JSONResponse(
        status_code=status_code,
        content=CourseReferenceFailureResponse(
            code=code,
            detail=detail,
        ).model_dump(mode="json"),
    )
