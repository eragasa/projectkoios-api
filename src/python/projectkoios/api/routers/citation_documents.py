from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Path,
    Request,
    UploadFile,
    status,
)
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.citation_document_models import (
    MAX_CITATION_DOCUMENT_PDF_BYTES,
    CitationDocumentApiErrorCode,
    CitationDocumentApiErrorEnvelope,
    CitationDocumentCatalogResponse,
    CitationDocumentProcessRequest,
    CitationDocumentProcessResponse,
    CitationDocumentReceiptResponse,
)
from projectkoios.api.citation_documents import (
    CitationDocumentNotFound,
    CitationDocumentPdfTooLarge,
    CitationDocumentProjectionConflict,
    CitationDocumentProvider,
    InvalidCitationDocumentRequest,
)
from projectkoios.api.provider_boundary import (
    MalformedProviderProjection,
    UnexpectedProviderFailure,
    validate_provider_projection,
    validated_provider_projection,
)
from projectkoios.api.provider_errors import ProviderUnavailable
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

_ERROR_RESPONSE: dict[str, Any] = {"model": CitationDocumentApiErrorEnvelope}
_PROVIDER_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        **_ERROR_RESPONSE,
        "description": "The citation-document owner failed unexpectedly.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        **_ERROR_RESPONSE,
        "description": "The citation-document owner returned invalid data.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        **_ERROR_RESPONSE,
        "description": "The citation-document owner is unavailable.",
    },
}
_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        **_ERROR_RESPONSE,
        "description": "The bounded request is invalid.",
    },
    status.HTTP_404_NOT_FOUND: {
        **_ERROR_RESPONSE,
        "description": "The citation-document item was not found.",
    },
    status.HTTP_409_CONFLICT: {
        **_ERROR_RESPONSE,
        "description": (
            "The request conflicts with the current owner projection."
        ),
    },
    **_PROVIDER_RESPONSES,
}


def create_citation_documents_router(
    provider: CitationDocumentProvider | None,
) -> APIRouter:
    router = APIRouter(
        prefix="/citation-documents",
        tags=["citation-documents"],
    )

    @router.get(
        "",
        response_model=CitationDocumentCatalogResponse,
        description=(
            "Local/private operator-only catalog. Do not expose this control "
            "surface on an untrusted network."
        ),
        responses=_PROVIDER_RESPONSES,
    )
    def read_catalog() -> CitationDocumentCatalogResponse:
        owner = _require_provider(provider)
        try:
            return validated_provider_projection(
                owner.read_catalog,
                CitationDocumentCatalogResponse,
            )
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error

    @router.post(
        "/{item_id}/source",
        response_model=CitationDocumentReceiptResponse,
        description=(
            "Local/private immutable PDF custody receipt only. Receipt does "
            "not authorize or start processing."
        ),
        responses={
            status.HTTP_413_CONTENT_TOO_LARGE: {
                **_ERROR_RESPONSE,
                "description": (
                    "The PDF exceeds the exact 50,000,000-byte custody limit."
                ),
            },
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
                **_ERROR_RESPONSE,
                "description": "The upload is not declared application/pdf.",
            },
            **_MUTATION_RESPONSES,
        },
    )
    async def receive_source(
        request: Request,
        item_id: Annotated[OpaqueId, Path()],
        source_pdf: Annotated[
            list[UploadFile],
            File(
                description=(
                    "Exactly one immutable PDF stream. The client filename is "
                    "ignored."
                ),
                json_schema_extra={
                    "minItems": 1,
                    "maxItems": 1,
                    "x-maximum-bytes": MAX_CITATION_DOCUMENT_PDF_BYTES,
                },
            ),
        ],
    ) -> CitationDocumentReceiptResponse:
        form_items = list((await request.form()).multi_items())
        if (
            len(form_items) != 1
            or form_items[0][0] != "source_pdf"
            or len(source_pdf) != 1
        ):
            for _, form_value in form_items:
                if isinstance(form_value, StarletteUploadFile):
                    await form_value.close()
            raise _invalid_request()
        owner = _require_provider(provider)
        upload = source_pdf[0]
        if upload.content_type != "application/pdf":
            await upload.close()
            raise _unsupported_media_type()
        try:
            value = await run_in_threadpool(
                lambda: owner.receive_source(
                    str(item_id),
                    upload.file,
                    media_type="application/pdf",
                )
            )
            return validate_provider_projection(
                value,
                CitationDocumentReceiptResponse,
            )
        except CitationDocumentNotFound as error:
            raise _item_not_found() from error
        except CitationDocumentPdfTooLarge as error:
            raise _pdf_too_large() from error
        except InvalidCitationDocumentRequest as error:
            raise _invalid_request() from error
        except CitationDocumentProjectionConflict as error:
            raise _projection_conflict() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error
        except Exception as error:
            raise _unexpected_failure() from error
        finally:
            await upload.close()

    @router.post(
        "/{item_id}/process-private",
        response_model=CitationDocumentProcessResponse,
        description=(
            "Explicit local-operator private processing command. Execution is "
            "synchronous and returns one terminal result; no retry is implied."
        ),
        responses=_MUTATION_RESPONSES,
    )
    async def process_private(
        item_id: Annotated[OpaqueId, Path()],
        request: CitationDocumentProcessRequest,
    ) -> CitationDocumentProcessResponse:
        owner = _require_provider(provider)
        try:
            value = await run_in_threadpool(
                lambda: owner.process_private(str(item_id), request)
            )
            return validate_provider_projection(
                value,
                CitationDocumentProcessResponse,
            )
        except CitationDocumentNotFound as error:
            raise _item_not_found() from error
        except InvalidCitationDocumentRequest as error:
            raise _invalid_request() from error
        except CitationDocumentProjectionConflict as error:
            raise _projection_conflict() from error
        except ProviderUnavailable as error:
            raise _provider_unavailable() from error
        except MalformedProviderProjection as error:
            raise _invalid_projection() from error
        except UnexpectedProviderFailure as error:
            raise _unexpected_failure() from error
        except Exception as error:
            raise _unexpected_failure() from error

    return router


def _require_provider(
    provider: CitationDocumentProvider | None,
) -> CitationDocumentProvider:
    if provider is None:
        raise _provider_unavailable()
    return provider


def _error(
    status_code: int,
    code: CitationDocumentApiErrorCode,
    detail: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "detail": detail},
    )


def _invalid_request() -> HTTPException:
    return _error(
        status.HTTP_400_BAD_REQUEST,
        CitationDocumentApiErrorCode.INVALID_REQUEST,
        "citation-document request is invalid",
    )


def _item_not_found() -> HTTPException:
    return _error(
        status.HTTP_404_NOT_FOUND,
        CitationDocumentApiErrorCode.ITEM_NOT_FOUND,
        "citation-document item was not found",
    )


def _projection_conflict() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        CitationDocumentApiErrorCode.PROJECTION_CONFLICT,
        "citation-document request conflicts with the current projection",
    )


def _pdf_too_large() -> HTTPException:
    return _error(
        status.HTTP_413_CONTENT_TOO_LARGE,
        CitationDocumentApiErrorCode.PDF_TOO_LARGE,
        "citation-document PDF exceeds 50000000 bytes",
    )


def _unsupported_media_type() -> HTTPException:
    return _error(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        CitationDocumentApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
        "citation-document upload must use application/pdf",
    )


def _provider_unavailable() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        CitationDocumentApiErrorCode.OWNER_UNAVAILABLE,
        "citation-document owner is unavailable",
    )


def _invalid_projection() -> HTTPException:
    return _error(
        status.HTTP_502_BAD_GATEWAY,
        CitationDocumentApiErrorCode.OWNER_MALFORMED,
        "citation-document owner returned an invalid projection",
    )


def _unexpected_failure() -> HTTPException:
    return _error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        CitationDocumentApiErrorCode.OWNER_FAILURE,
        "citation-document owner failed unexpectedly",
    )
