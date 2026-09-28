from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.equation_review import (
    EquationReviewNotFound,
    EquationReviewRepository,
    EquationReviewUnavailable,
    InvalidEquationReviewDecision,
)
from projectkoios.api.equation_review_models import (
    EquationReviewDecisionRequest,
    EquationReviewQueueResponse,
)
from projectkoios.api.error_models import ApiErrorResponse

_BINARY_RESPONSE_HEADERS: dict[str, dict[str, Any]] = {
    "Content-Disposition": {
        "description": "Always `inline`; artifact filenames are never exposed.",
        "schema": {"type": "string", "const": "inline"},
    },
    "X-Content-Type-Options": {
        "description": "Prevents media-type sniffing.",
        "schema": {"type": "string", "const": "nosniff"},
    },
}
_UNAVAILABLE_RESPONSE: dict[str, Any] = {
    "model": ApiErrorResponse,
    "description": "Configured equation-review evidence is unavailable.",
}
_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": ApiErrorResponse,
    "description": "The equation-review identity is not configured.",
}


def create_equation_review_router(
    repository: EquationReviewRepository,
) -> APIRouter:
    router = APIRouter(
        prefix="/equation-reviews",
        tags=["equation-reviews"],
    )

    @router.get(
        "",
        response_model=EquationReviewQueueResponse,
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def queue(
        document_id: Annotated[OpaqueId, Query()],
    ) -> EquationReviewQueueResponse:
        try:
            return repository.queue(str(document_id))
        except EquationReviewNotFound as error:
            raise _document_not_found() from error
        except EquationReviewUnavailable as error:
            raise _evidence_unavailable() from error

    @router.get(
        "/{candidate_id}/region",
        response_class=Response,
        responses={
            status.HTTP_200_OK: {
                "description": (
                    "Content-addressed PNG, JPEG, or WebP evidence, fully "
                    "buffered and limited to exactly 20,000,000 bytes."
                ),
                "headers": _BINARY_RESPONSE_HEADERS,
                "content": {
                    media_type: {
                        "schema": {
                            "type": "string",
                            "format": "binary",
                            "minLength": 1,
                            "x-maximum-bytes": 20_000_000,
                        }
                    }
                    for media_type in (
                        "image/jpeg",
                        "image/png",
                        "image/webp",
                    )
                },
            },
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def region(
        candidate_id: Annotated[OpaqueId, Path()],
    ) -> Response:
        try:
            resource = repository.region(str(candidate_id))
        except EquationReviewNotFound as error:
            raise _candidate_not_found() from error
        except EquationReviewUnavailable as error:
            raise _evidence_unavailable() from error
        return Response(
            content=resource.body,
            media_type=resource.media_type,
            headers={
                "Content-Disposition": "inline",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.put(
        "/{candidate_id}/decision",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        response_model=ApiErrorResponse,
        response_description=(
            "Equation decision persistence has no applications-owned adapter."
        ),
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_409_CONFLICT: {
                "model": ApiErrorResponse,
                "description": (
                    "The request is not bound to the displayed proposal."
                ),
            },
        },
    )
    def decide(
        candidate_id: Annotated[OpaqueId, Path()],
        request: EquationReviewDecisionRequest,
    ) -> ApiErrorResponse:
        try:
            repository.decision_binding(str(candidate_id), request)
        except EquationReviewNotFound as error:
            raise _candidate_not_found() from error
        except EquationReviewUnavailable as error:
            raise _evidence_unavailable() from error
        except InvalidEquationReviewDecision as error:
            raise _invalid_decision() from error
        return ApiErrorResponse(
            detail="equation review decision persistence is unavailable"
        )

    return router


def _document_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="equation review document was not found",
    )


def _candidate_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="equation review candidate was not found",
    )


def _evidence_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="equation review evidence is unavailable",
    )


def _invalid_decision() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="equation review decision does not match candidate evidence",
    )
