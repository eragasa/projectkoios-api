from __future__ import annotations

import tempfile
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, status
from projectkoios.api.project_reference_intake import (
    ProjectReferenceIntakeConflict,
    ProjectReferenceIntakeInvalidPdf,
    ProjectReferenceIntakeMalformed,
    ProjectReferenceIntakeNotFound,
    ProjectReferenceIntakePdfTooLarge,
    ProjectReferenceIntakeProvider,
    ProjectReferenceIntakeUnavailable,
)
from projectkoios.api.project_reference_intake_models import (
    Citekey,
    MissingPdfItemResponse,
    MissingPdfListResponse,
    ProvideMissingPdfResponse,
)
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

CitekeyPath = Annotated[
    Citekey,
    Path(description="BibTeX citekey returned by the missing-PDF list."),
]


def create_project_reference_intake_router(
    provider: ProjectReferenceIntakeProvider,
) -> APIRouter:
    router = APIRouter(
        prefix="/project-reference-intake/ksdft2effmass",
        tags=["project-reference-intake"],
    )

    @router.get(
        "/missing-pdfs",
        response_model=MissingPdfListResponse,
    )
    def missing_pdfs() -> MissingPdfListResponse:
        try:
            owner = provider.missing_pdfs()
            items = tuple(
                MissingPdfItemResponse(
                    citekey=item.citekey,
                    entry_type=item.entry_type,
                    title=item.title,
                    authors=item.authors,
                    year=item.year,
                )
                for item in owner.missing
            )
            return MissingPdfListResponse(
                total_references=(
                    owner.required_count + owner.not_applicable_count
                ),
                required_pdf_count=owner.required_count,
                bound_pdf_count=owner.bound_count,
                missing_pdf_count=len(items),
                not_applicable_count=owner.not_applicable_count,
                max_pdf_bytes=provider.max_pdf_bytes,
                items=items,
            )
        except ProjectReferenceIntakeNotFound as error:
            raise _not_found() from error
        except (ProjectReferenceIntakeMalformed, ValidationError) as error:
            raise _malformed() from error
        except ProjectReferenceIntakeUnavailable as error:
            raise _unavailable() from error

    @router.post(
        "/missing-pdfs/{citekey}/document",
        response_model=ProvideMissingPdfResponse,
    )
    async def provide_pdf(
        citekey: CitekeyPath,
        request: Request,
    ) -> ProvideMissingPdfResponse:
        _require_pdf_media_type(request)
        declared_size = _declared_size(
            request,
            max_pdf_bytes=provider.max_pdf_bytes,
        )
        try:
            with tempfile.TemporaryFile(mode="w+b") as stream:
                observed_size = 0
                async for block in request.stream():
                    observed_size += len(block)
                    if observed_size > provider.max_pdf_bytes:
                        raise _too_large()
                    stream.write(block)
                if observed_size == 0:
                    raise _invalid_pdf()
                if declared_size is not None and observed_size != declared_size:
                    raise _invalid_length()
                stream.flush()
                stream.seek(0)
                if stream.read(5) != b"%PDF-":
                    raise _invalid_pdf()
                stream.seek(0)
                owner = await run_in_threadpool(
                    provider.provide_pdf,
                    citekey=str(citekey),
                    stream=stream,
                    declared_byte_size=observed_size,
                )
            return ProvideMissingPdfResponse(
                citekey=owner.citekey,
                byte_size=owner.byte_size,
                receipt_disposition=owner.receipt_disposition,
                binding_disposition=owner.binding_disposition,
            )
        except ProjectReferenceIntakePdfTooLarge as error:
            raise _too_large() from error
        except ProjectReferenceIntakeInvalidPdf as error:
            raise _invalid_pdf() from error
        except ProjectReferenceIntakeNotFound as error:
            raise _not_found() from error
        except ProjectReferenceIntakeConflict as error:
            raise _conflict() from error
        except (ProjectReferenceIntakeMalformed, ValidationError) as error:
            raise _malformed() from error
        except ProjectReferenceIntakeUnavailable as error:
            raise _unavailable() from error

    return router


def _require_pdf_media_type(request: Request) -> None:
    if request.headers.get("content-type", "").casefold() != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="request body must be application/pdf",
        )


def _declared_size(request: Request, *, max_pdf_bytes: int) -> int | None:
    value = request.headers.get("content-length")
    if value is None:
        return None
    if not value.isascii() or not value.isdecimal():
        raise _invalid_length()
    size = int(value)
    if size > max_pdf_bytes:
        raise _too_large()
    if size < 1:
        raise _invalid_length()
    return size


def _invalid_length() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="PDF content length is invalid",
    )


def _invalid_pdf() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="request body is not a valid PDF upload",
    )


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail="PDF upload exceeds the configured byte limit",
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="project reference was not found",
    )


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="project reference already has a different PDF binding",
    )


def _malformed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="reference owner returned invalid project metadata",
    )


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="reference owner is unavailable",
    )
