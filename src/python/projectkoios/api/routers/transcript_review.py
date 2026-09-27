from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from projectkoios.api.transcript_review import (
    TranscriptReviewProvider,
    TranscriptReviewResource,
)
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewQueueResponse,
)

_MAX_PDF_BYTES = 100_000_000
_MAX_PREVIEW_BYTES = 20_000_000
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
_PREVIEW_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_DOCUMENT_ID = Path(
    min_length=1,
    max_length=256,
    pattern=_IDENTIFIER_PATTERN,
)
_ASSET_ID = Path(
    min_length=1,
    max_length=256,
    pattern=_IDENTIFIER_PATTERN,
)
_NOT_FOUND_RESPONSE = {
    "model": ApiErrorResponse,
    "description": "The requested transcript review projection was not found.",
}
_UNAVAILABLE_RESPONSE = {
    "model": ApiErrorResponse,
    "description": "No transcript review owner adapter is available.",
}


def create_transcript_review_router(
    provider: TranscriptReviewProvider | None,
) -> APIRouter:
    router = APIRouter(
        prefix="/transcript-reviews",
        tags=["transcript-reviews"],
    )

    @router.get(
        "",
        response_model=TranscriptReviewQueueResponse,
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def read_queue() -> TranscriptReviewQueueResponse:
        owner = _require_provider(provider)
        try:
            return owner.read_queue()
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error

    @router.get(
        "/{document_id}/source",
        response_class=Response,
        responses={
            status.HTTP_200_OK: {
                "description": "Bounded authoritative source PDF.",
                "content": {
                    "application/pdf": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
            },
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def read_source(
        document_id: Annotated[str, _DOCUMENT_ID],
    ) -> Response:
        owner = _require_provider(provider)
        try:
            resource = owner.read_source(document_id)
        except ProjectionNotFound as error:
            raise _source_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        _require_resource(
            resource,
            allowed_media_types=frozenset({"application/pdf"}),
            maximum_bytes=_MAX_PDF_BYTES,
        )
        return Response(content=resource.body, media_type=resource.media_type)

    @router.get(
        "/{document_id}/assets/{asset_id}",
        response_class=Response,
        responses={
            status.HTTP_200_OK: {
                "description": "Bounded transcript review preview image.",
                "content": {
                    media_type: {
                        "schema": {"type": "string", "format": "binary"}
                    }
                    for media_type in sorted(_PREVIEW_MEDIA_TYPES)
                },
            },
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def read_preview(
        document_id: Annotated[str, _DOCUMENT_ID],
        asset_id: Annotated[str, _ASSET_ID],
    ) -> Response:
        owner = _require_provider(provider)
        try:
            resource = owner.read_preview(document_id, asset_id)
        except ProjectionNotFound as error:
            raise _preview_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        _require_resource(
            resource,
            allowed_media_types=_PREVIEW_MEDIA_TYPES,
            maximum_bytes=_MAX_PREVIEW_BYTES,
        )
        return Response(content=resource.body, media_type=resource.media_type)

    @router.get(
        "/{document_id}",
        response_model=TranscriptReviewDocumentResponse,
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
        },
    )
    def read_document(
        document_id: Annotated[str, _DOCUMENT_ID],
    ) -> TranscriptReviewDocumentResponse:
        owner = _require_provider(provider)
        try:
            return owner.read_document(document_id)
        except ProjectionNotFound as error:
            raise _document_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error

    return router


def _require_provider(
    provider: TranscriptReviewProvider | None,
) -> TranscriptReviewProvider:
    if provider is None:
        raise _provider_unavailable()
    return provider


def _require_resource(
    resource: TranscriptReviewResource,
    *,
    allowed_media_types: frozenset[str],
    maximum_bytes: int,
) -> None:
    if (
        resource.media_type not in allowed_media_types
        or len(resource.body) > maximum_bytes
    ):
        raise _provider_unavailable()


def _provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="transcript review provider is unavailable",
    )


def _document_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="transcript review document was not found",
    )


def _source_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="transcript review source was not found",
    )


def _preview_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="transcript review asset was not found",
    )
