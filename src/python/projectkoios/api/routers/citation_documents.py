from __future__ import annotations

import tempfile
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, BinaryIO, cast

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.routing import APIRoute
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
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

MAX_CITATION_DOCUMENT_PROCESS_REQUEST_BYTES = 64_000
_PDF_MAGIC = b"%PDF-"
_OPAQUE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
_ITEM_ID_ADAPTER = TypeAdapter(OpaqueId)
CitationDocumentItemId = Annotated[
    str,
    Path(
        min_length=1,
        max_length=256,
        pattern=_OPAQUE_ID_PATTERN,
    ),
]


def _inline_process_request_schema() -> dict[str, Any]:
    schema = CitationDocumentProcessRequest.model_json_schema()
    definitions = cast(dict[str, Any], schema.pop("$defs", {}))

    def dereference(value: object) -> object:
        if isinstance(value, list):
            return [dereference(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.rsplit("/", 1)[-1]
            resolved = dict(definitions[name])
            resolved.update(
                {key: item for key, item in value.items() if key != "$ref"}
            )
            return dereference(resolved)
        return {key: dereference(item) for key, item in value.items()}

    inlined = cast(dict[str, Any], dereference(schema))
    inlined["x-maximum-bytes"] = MAX_CITATION_DOCUMENT_PROCESS_REQUEST_BYTES
    return inlined


_PROCESS_REQUEST_SCHEMA = _inline_process_request_schema()
_ERROR_RESPONSE: dict[str, Any] = {"model": CitationDocumentApiErrorEnvelope}
_VALIDATION_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        **_ERROR_RESPONSE,
        "description": "Request validation failed without reflecting input.",
    }
}
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
    **_VALIDATION_RESPONSE,
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


class CitationDocumentRoute(APIRoute):
    """Sanitize every framework validation failure on this private surface."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def sanitized(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as error:
                raise _validation_error() from error

        return sanitized


def create_citation_documents_router(
    provider: CitationDocumentProvider | None,
) -> APIRouter:
    router = APIRouter(
        prefix="/citation-documents",
        tags=["citation-documents"],
        route_class=CitationDocumentRoute,
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
            "Local/private immutable raw PDF custody receipt only. Receipt "
            "does not authorize or start processing."
        ),
        responses={
            status.HTTP_413_CONTENT_TOO_LARGE: {
                **_ERROR_RESPONSE,
                "description": (
                    "The PDF exceeds the exact 50,000,000-byte transport and "
                    "custody limit."
                ),
            },
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
                **_ERROR_RESPONSE,
                "description": "The body is not application/pdf.",
            },
            **_MUTATION_RESPONSES,
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/pdf": {
                        "schema": {
                            "type": "string",
                            "format": "binary",
                            "minLength": len(_PDF_MAGIC),
                            "x-maximum-bytes": (
                                MAX_CITATION_DOCUMENT_PDF_BYTES
                            ),
                        }
                    }
                },
            }
        },
    )
    async def receive_source(
        request: Request,
        item_id: CitationDocumentItemId,
    ) -> CitationDocumentReceiptResponse:
        validated_item_id = _validated_item_id(item_id)
        owner = _require_provider(provider)
        source = await _receive_bounded_pdf(request)
        try:
            provider_value = await run_in_threadpool(
                lambda: owner.receive_source(
                    validated_item_id,
                    source,
                    media_type="application/pdf",
                )
            )
            return validate_provider_projection(
                provider_value,
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
            source.close()

    @router.post(
        "/{item_id}/process-private",
        response_model=CitationDocumentProcessResponse,
        description=(
            "Explicit local-operator private processing command. Execution is "
            "synchronous and returns one terminal result; no retry is implied."
        ),
        responses={
            status.HTTP_413_CONTENT_TOO_LARGE: {
                **_ERROR_RESPONSE,
                "description": (
                    "The JSON request exceeds the exact 64,000-byte transport "
                    "limit."
                ),
            },
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
                **_ERROR_RESPONSE,
                "description": "The body is not application/json.",
            },
            **_MUTATION_RESPONSES,
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": _PROCESS_REQUEST_SCHEMA}
                },
            }
        },
    )
    async def process_private(
        request: Request,
        item_id: CitationDocumentItemId,
    ) -> CitationDocumentProcessResponse:
        validated_item_id = _validated_item_id(item_id)
        owner = _require_provider(provider)
        process_request = await _receive_process_request(request)
        try:
            provider_value = await run_in_threadpool(
                lambda: owner.process_private(
                    validated_item_id,
                    process_request,
                )
            )
            return validate_provider_projection(
                provider_value,
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


async def _receive_bounded_pdf(request: Request) -> BinaryIO:
    content_type = request.headers.get("content-type", "").partition(";")[0]
    if content_type.strip().lower() != "application/pdf":
        raise _unsupported_media_type()
    declared_length = _declared_length(request)
    if (
        declared_length is not None
        and declared_length > MAX_CITATION_DOCUMENT_PDF_BYTES
    ):
        raise _pdf_too_large()

    source = cast(BinaryIO, tempfile.TemporaryFile(mode="w+b"))
    observed_length = 0
    leading = bytearray()
    try:
        async for chunk in request.stream():
            observed_length += len(chunk)
            if observed_length > MAX_CITATION_DOCUMENT_PDF_BYTES:
                raise _pdf_too_large()
            if len(leading) < len(_PDF_MAGIC):
                required = len(_PDF_MAGIC) - len(leading)
                leading.extend(chunk[:required])
            source.write(chunk)
        if declared_length is not None and declared_length != observed_length:
            raise _invalid_request()
        if bytes(leading) != _PDF_MAGIC:
            raise _invalid_request()
        source.seek(0)
        return source
    except BaseException:
        source.close()
        raise


async def _receive_process_request(
    request: Request,
) -> CitationDocumentProcessRequest:
    content_type = request.headers.get("content-type", "").partition(";")[0]
    if content_type.strip().lower() != "application/json":
        raise _unsupported_media_type()
    content = await _receive_bounded_bytes(
        request,
        maximum=MAX_CITATION_DOCUMENT_PROCESS_REQUEST_BYTES,
    )
    try:
        return CitationDocumentProcessRequest.model_validate_json(
            content,
            strict=True,
        )
    except (ValidationError, ValueError) as error:
        raise _invalid_request() from error


async def _receive_bounded_bytes(request: Request, *, maximum: int) -> bytes:
    declared_length = _declared_length(request)
    if declared_length is not None and declared_length > maximum:
        raise _request_too_large()
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            raise _request_too_large()
        content.extend(chunk)
    if declared_length is not None and declared_length != len(content):
        raise _invalid_request()
    if not content:
        raise _invalid_request()
    return bytes(content)


def _declared_length(request: Request) -> int | None:
    value = request.headers.get("content-length")
    if value is None:
        return None
    try:
        result = int(value)
    except ValueError as error:
        raise _invalid_request() from error
    if result < 0:
        raise _invalid_request()
    return result


def _validated_item_id(value: str) -> str:
    try:
        return str(_ITEM_ID_ADAPTER.validate_python(value, strict=True))
    except ValidationError as error:
        raise _validation_error() from error


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


def _validation_error() -> HTTPException:
    return _error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        CitationDocumentApiErrorCode.INVALID_REQUEST,
        "citation-document request validation failed",
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


def _request_too_large() -> HTTPException:
    return _error(
        status.HTTP_413_CONTENT_TOO_LARGE,
        CitationDocumentApiErrorCode.INVALID_REQUEST,
        "citation-document request exceeds its byte limit",
    )


def _unsupported_media_type() -> HTTPException:
    return _error(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        CitationDocumentApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
        "citation-document request uses an unsupported media type",
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
