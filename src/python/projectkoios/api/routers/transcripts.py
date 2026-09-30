from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, status
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.error_models import ApiErrorResponse
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    validated_provider_projection,
)
from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
)
from projectkoios.api.transcripts import TranscriptProvider

_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": ApiErrorResponse,
    "description": "The requested configured transcript was not found.",
}
_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ApiErrorResponse,
        "description": "The transcript provider failed unexpectedly.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ApiErrorResponse,
        "description": "The transcript provider returned invalid data.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorResponse,
        "description": "The configured transcript owner is unavailable.",
    },
}


def create_transcripts_router(provider: TranscriptProvider | None) -> APIRouter:
    router = APIRouter(prefix="/transcripts", tags=["transcripts"])

    @router.get(
        "",
        response_model=TranscriptCollectionResponse,
        responses=_PROVIDER_RESPONSES,
    )
    def read_collection() -> TranscriptCollectionResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                owner.read_collection,
                TranscriptCollectionResponse,
            )
        except ProjectionNotFound as error:
            raise _unexpected_failure() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    @router.get(
        "/{document_id}",
        response_model=TranscriptDocumentResponse,
        responses={
            status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
            **_PROVIDER_RESPONSES,
        },
    )
    def read_document(
        document_id: Annotated[OpaqueId, Path()],
    ) -> TranscriptDocumentResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                lambda: owner.read_document(str(document_id)),
                TranscriptDocumentResponse,
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
    provider: TranscriptProvider | None,
) -> TranscriptProvider:
    if provider is None:
        raise _provider_unavailable()
    return provider


def _provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="transcript provider is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="transcript provider returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="transcript provider failed unexpectedly",
    )


def _document_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="transcript document was not found",
    )
