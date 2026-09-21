from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from projectkoios.api.literature_review import (
    InvalidProvidedReference,
    LiteratureReviewRepository,
    LiteratureReviewUnavailable,
)
from projectkoios.api.literature_review_models import (
    LiteratureReviewProgressResponse,
    ProvidedReferenceListResponse,
    ProvidedReferenceResponse,
)

_MAX_REFERENCE_BYTES = 100_000_000


def create_literature_review_router(
    repository: LiteratureReviewRepository,
) -> APIRouter:
    router = APIRouter(prefix="/literature-review", tags=["literature review"])

    @router.get("/progress")
    def progress() -> LiteratureReviewProgressResponse:
        try:
            return repository.progress()
        except LiteratureReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @router.get("/references")
    def references() -> ProvidedReferenceListResponse:
        try:
            return repository.provided_references()
        except LiteratureReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    @router.post("/references", status_code=status.HTTP_201_CREATED)
    async def provide_reference(
        claim_id: Annotated[str, Form(min_length=1, max_length=128)],
        citation_label: Annotated[str, Form(min_length=1, max_length=128)],
        reference_pdf: Annotated[UploadFile, File()],
        doi_or_url: Annotated[str | None, Form(max_length=1_000)] = None,
        note: Annotated[str, Form(max_length=4_000)] = "",
    ) -> ProvidedReferenceResponse:
        if reference_pdf.content_type != "application/pdf":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="reference file must use application/pdf",
            )
        body = bytearray()
        try:
            while chunk := await reference_pdf.read(1024 * 1024):
                body.extend(chunk)
                if len(body) > _MAX_REFERENCE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="reference PDF exceeds 100000000 bytes",
                    )
        finally:
            await reference_pdf.close()
        try:
            return repository.provide_reference(
                claim_id=claim_id,
                citation_label=citation_label,
                doi_or_url=doi_or_url,
                note=note,
                pdf_bytes=bytes(body),
            )
        except InvalidProvidedReference as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except LiteratureReviewUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    return router
