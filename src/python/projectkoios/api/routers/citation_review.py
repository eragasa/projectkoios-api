from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from projectkoios.api.citation_review import (
    CitationReviewNotFound,
    CitationReviewRepository,
    CitationReviewUnavailable,
    InvalidCitationDecision,
)
from projectkoios.api.citation_review_models import (
    CitationDecisionRequest,
    CitationDecisionResponse,
    CitationReviewDetailResponse,
    CitationReviewQueueResponse,
)


def create_citation_review_router(
    repository: CitationReviewRepository,
) -> APIRouter:
    router = APIRouter(prefix="/citation-reviews", tags=["citation reviews"])

    @router.get("")
    def queue() -> CitationReviewQueueResponse:
        try:
            return repository.queue()
        except CitationReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @router.get("/sources/{source_name}", response_class=FileResponse)
    def source(source_name: str) -> FileResponse:
        try:
            path = repository.source_path(source_name)
        except CitationReviewNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="citation source was not found",
            ) from error
        except CitationReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return FileResponse(path, media_type="application/pdf")

    @router.get("/{claim_id}")
    def detail(claim_id: str) -> CitationReviewDetailResponse:
        try:
            return repository.detail(claim_id)
        except CitationReviewNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="citation review claim was not found",
            ) from error
        except CitationReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @router.put("/{claim_id}/decision")
    def decide(
        claim_id: str,
        request: CitationDecisionRequest,
    ) -> CitationDecisionResponse:
        try:
            return repository.decide(claim_id, request)
        except CitationReviewNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="citation review claim was not found",
            ) from error
        except InvalidCitationDecision as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except CitationReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    return router
