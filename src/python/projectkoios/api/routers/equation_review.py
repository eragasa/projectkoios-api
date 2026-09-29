from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response, status
from fastapi.responses import JSONResponse
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.equation_review import (
    EquationReviewNotFound,
    EquationReviewRepository,
    EquationReviewUnavailable,
    InvalidEquationReviewDecision,
)
from projectkoios.api.equation_review_boundary import (
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceStale,
    EquationReviewNoncanonicalLatex,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review_models import (
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewFailureCode,
    EquationReviewFailureResponse,
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
_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": ApiErrorResponse,
    "description": "The equation-review identity is not configured.",
}
_CONFLICT_RESPONSE: dict[str, Any] = {
    "model": EquationReviewFailureResponse,
    "description": (
        "The proposal, immutable evidence, expected revision, or concurrent "
        "append does not match."
    ),
}
_UNAVAILABLE_RESPONSE: dict[str, Any] = {
    "model": EquationReviewFailureResponse,
    "description": (
        "Configured evidence, the owner root, or complete append output is "
        "unavailable."
    ),
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
            status.HTTP_409_CONFLICT: _CONFLICT_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def queue(
        document_id: Annotated[OpaqueId, Query()],
    ) -> EquationReviewQueueResponse | Response:
        try:
            return repository.queue(str(document_id))
        except EquationReviewNotFound:
            return _not_found("equation review document was not found")
        except EquationReviewUnavailable:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.OWNER_UNAVAILABLE,
                "equation review evidence is unavailable",
            )
        except EquationReviewEvidenceStale:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.EVIDENCE_STALE,
                "equation review evidence is stale",
            )
        except EquationReviewPartialOutput:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.PARTIAL_OUTPUT,
                "equation review output is partial or malformed",
            )
        except EquationReviewOwnerUnavailable:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.OWNER_UNAVAILABLE,
                "equation review owner is unavailable",
            )

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
        except EquationReviewNotFound:
            return _not_found("equation review candidate was not found")
        except EquationReviewUnavailable:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.OWNER_UNAVAILABLE,
                "equation review evidence is unavailable",
            )
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
        response_model=EquationReviewDecisionResponse,
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_409_CONFLICT: _CONFLICT_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def decide(
        candidate_id: Annotated[OpaqueId, Path()],
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse | Response:
        try:
            return repository.decide(str(candidate_id), request)
        except EquationReviewNotFound:
            return _not_found("equation review candidate was not found")
        except EquationReviewUnavailable:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.OWNER_UNAVAILABLE,
                "equation review evidence is unavailable",
            )
        except InvalidEquationReviewDecision:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.PROPOSAL_STALE,
                "equation review proposal does not match candidate evidence",
            )
        except EquationReviewEvidenceStale:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.EVIDENCE_STALE,
                "equation review evidence is stale",
            )
        except EquationReviewRevisionStale:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.REVISION_STALE,
                "equation review revision is stale",
            )
        except EquationReviewNoncanonicalLatex:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.REVIEWER_LATEX_NONCANONICAL,
                "reviewer LaTeX must be a canonical math body",
            )
        except EquationReviewRenderStale:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.RENDER_STALE,
                "equation review render confirmation is stale",
            )
        except EquationReviewEditAfterRender:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.EDIT_AFTER_RENDER,
                "equation review content changed after render",
            )
        except EquationReviewConcurrentDecision:
            return _failure(
                status.HTTP_409_CONFLICT,
                EquationReviewFailureCode.CONCURRENT_DECISION,
                "a different equation review decision won concurrently",
            )
        except EquationReviewPartialOutput:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.PARTIAL_OUTPUT,
                "equation review output is partial or malformed",
            )
        except EquationReviewOwnerUnavailable:
            return _failure(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                EquationReviewFailureCode.OWNER_UNAVAILABLE,
                "equation review owner is unavailable",
            )

    return router


def _not_found(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ApiErrorResponse(detail=detail).model_dump(mode="json"),
    )


def _failure(
    status_code: int,
    code: EquationReviewFailureCode,
    detail: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=EquationReviewFailureResponse(
            code=code,
            detail=detail,
        ).model_dump(mode="json"),
    )
