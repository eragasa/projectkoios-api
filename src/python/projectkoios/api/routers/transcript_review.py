from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Response, status
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    invoke_provider,
    validated_provider_projection,
)
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
_PREVIEW_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_BINARY_RESPONSE_HEADERS: dict[str, dict[str, Any]] = {
    "Content-Disposition": {
        "description": "Always `inline`; provider filenames are never exposed.",
        "schema": {"type": "string", "const": "inline"},
    },
    "X-Content-Type-Options": {
        "description": "Prevents media-type sniffing.",
        "schema": {"type": "string", "const": "nosniff"},
    },
}
_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": ApiErrorResponse,
    "description": "The requested transcript review projection was not found.",
}
_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": (
            "The transcript review owner adapter failed unexpectedly."
        ),
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ApiErrorResponse,
        "description": (
            "The transcript review owner adapter returned invalid data."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorResponse,
        "description": "No transcript review owner adapter is available.",
    },
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
        responses=_PROVIDER_RESPONSES,
    )
    def read_queue() -> TranscriptReviewQueueResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                owner.read_queue,
                TranscriptReviewQueueResponse,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    @router.get(
        "/{document_id}/source",
        response_class=Response,
        responses={
            status.HTTP_200_OK: {
                "description": (
                    "Nonempty PDF with a `%PDF-` signature, fully buffered in "
                    "memory and limited to exactly 100,000,000 bytes."
                ),
                "headers": _BINARY_RESPONSE_HEADERS,
                "content": {
                    "application/pdf": {
                        "schema": {
                            "type": "string",
                            "format": "binary",
                            "minLength": 1,
                            "x-maximum-bytes": _MAX_PDF_BYTES,
                        }
                    }
                },
            },
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            **_PROVIDER_RESPONSES,
        },
    )
    def read_source(
        document_id: Annotated[OpaqueId, Path()],
    ) -> Response:
        owner = _require_provider(provider)
        try:
            resource = invoke_provider(
                lambda: owner.read_source(str(document_id))
            )
            validated = _validated_resource(
                resource,
                allowed_media_types=frozenset({"application/pdf"}),
                maximum_bytes=_MAX_PDF_BYTES,
            )
        except ProjectionNotFound as error:
            raise _source_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error
        return _binary_response(validated)

    @router.get(
        "/{document_id}/assets/{asset_id}",
        response_class=Response,
        responses={
            status.HTTP_200_OK: {
                "description": (
                    "Nonempty PNG, JPEG, or WebP with matching magic bytes, "
                    "fully buffered in memory and limited to exactly "
                    "20,000,000 bytes."
                ),
                "headers": _BINARY_RESPONSE_HEADERS,
                "content": {
                    media_type: {
                        "schema": {
                            "type": "string",
                            "format": "binary",
                            "minLength": 1,
                            "x-maximum-bytes": _MAX_PREVIEW_BYTES,
                        }
                    }
                    for media_type in sorted(_PREVIEW_MEDIA_TYPES)
                },
            },
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            **_PROVIDER_RESPONSES,
        },
    )
    def read_preview(
        document_id: Annotated[OpaqueId, Path()],
        asset_id: Annotated[OpaqueId, Path()],
    ) -> Response:
        owner = _require_provider(provider)
        try:
            resource = invoke_provider(
                lambda: owner.read_preview(
                    str(document_id),
                    str(asset_id),
                )
            )
            validated = _validated_resource(
                resource,
                allowed_media_types=_PREVIEW_MEDIA_TYPES,
                maximum_bytes=_MAX_PREVIEW_BYTES,
            )
        except ProjectionNotFound as error:
            raise _preview_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error
        return _binary_response(validated)

    @router.get(
        "/{document_id}",
        response_model=TranscriptReviewDocumentResponse,
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            **_PROVIDER_RESPONSES,
        },
    )
    def read_document(
        document_id: Annotated[OpaqueId, Path()],
    ) -> TranscriptReviewDocumentResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                lambda: owner.read_document(str(document_id)),
                TranscriptReviewDocumentResponse,
            )
        except ProjectionNotFound as error:
            raise _document_not_found() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    return router


def _require_provider(
    provider: TranscriptReviewProvider | None,
) -> TranscriptReviewProvider:
    if provider is None:
        raise _provider_unavailable()
    return provider


def _validated_resource(
    resource: object,
    *,
    allowed_media_types: frozenset[str],
    maximum_bytes: int,
) -> TranscriptReviewResource:
    if (
        type(resource) is not TranscriptReviewResource
        or type(resource.body) is not bytes
        or type(resource.media_type) is not str
        or not resource.body
        or len(resource.body) > maximum_bytes
        or resource.media_type not in allowed_media_types
        or not _has_matching_magic(resource.media_type, resource.body)
    ):
        raise MalformedProviderProjection
    return TranscriptReviewResource(
        body=resource.body,
        media_type=resource.media_type,
    )


def _has_matching_magic(media_type: str, body: bytes) -> bool:
    if media_type == "application/pdf":
        return body.startswith(b"%PDF-")
    if media_type == "image/png":
        return body.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return body.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return (
            len(body) >= 12
            and body.startswith(b"RIFF")
            and body[8:12] == b"WEBP"
        )
    return False


def _binary_response(resource: TranscriptReviewResource) -> Response:
    return Response(
        content=resource.body,
        media_type=resource.media_type,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="transcript review provider is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="transcript review provider returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="transcript review provider failed unexpectedly",
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
