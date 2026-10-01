from __future__ import annotations

from typing import BinaryIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.citation_document_models import (
    CitationDocumentCatalogResponse,
    CitationDocumentItemResponse,
    CitationDocumentProcessRequest,
    CitationDocumentProcessResponse,
    CitationDocumentProjectionResponse,
    CitationDocumentReceiptResponse,
    CitationIdentityItemResponse,
    CitationSourceDocumentLinkResponse,
    CitationSourceDocumentResponse,
)
from projectkoios.api.citation_documents import (
    CitationDocumentNotFound,
    CitationDocumentPdfTooLarge,
    CitationDocumentProjectionConflict,
)
from projectkoios.api.routers.citation_documents import (
    create_citation_documents_router,
)
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
)
from pydantic import ValidationError


def _identity_item() -> CitationIdentityItemResponse:
    return CitationIdentityItemResponse(
        item_id="identity-item:sha256:" + "1" * 64,
        requested_identity_id="reference:sha256:" + "2" * 64,
        projection_id="identity-projection:sha256:" + "3" * 64,
        status="accepted-active-canonical",
        reference_id="reference:sha256:" + "2" * 64,
        canonical_citekey="example2026",
        successor_reference_ids=(),
    )


def _item() -> CitationDocumentItemResponse:
    return CitationDocumentItemResponse(
        item_id="citation-document-projection-item:sha256:" + "4" * 64,
        target_snapshot_id="citation-snapshot:" + "5" * 64,
        identity_projection_id="identity-projection:sha256:" + "3" * 64,
        literal_citekey="example2026",
        occurrence_ids=("citation-occurrence:" + "6" * 64,),
        bibliography_membership_status="defined",
        key_resolution_status="resolved",
        identity_items=(_identity_item(),),
        document_status="not-observed",
        source_document_ids=(),
        source_document_link_ids=(),
    )


def _catalog() -> CitationDocumentCatalogResponse:
    item = _item()
    return CitationDocumentCatalogResponse(
        request_id="citation-document-projection-request:sha256:" + "7" * 64,
        result_id="citation-document-projection-result:sha256:" + "8" * 64,
        projection=CitationDocumentProjectionResponse(
            contract_id="projectkoios.references.citation-document-projection",
            target_snapshot_id=item.target_snapshot_id,
            target_projection_id="citation-target-projection:sha256:"
            + "9" * 64,
            bibliography_binding_ids=(),
            identity_projection_id=item.identity_projection_id,
            document_observation_ids=(),
            source_document_link_ids=(),
            source_documents=(),
            items=(item,),
            source_gaps=(),
            limitations=("not-ingestion-status",),
            projection_id="citation-document-projection:sha256:" + "a" * 64,
        ),
    )


def _receipt() -> CitationDocumentReceiptResponse:
    return CitationDocumentReceiptResponse(
        source_document=CitationSourceDocumentResponse(
            source_document_id="private-pdf:sha256:" + "b" * 64,
            sha256="b" * 64,
            byte_size=14,
            media_type="application/pdf",
            descriptor_id="citation-source-document-descriptor:sha256:"
            + "c" * 64,
        ),
        receipt_id="citation-document-receipt:sha256:" + "d" * 64,
    )


def _process_request() -> CitationDocumentProcessRequest:
    return CitationDocumentProcessRequest(
        expected_projection_id=_catalog().projection.projection_id,
        identity_item_id=_identity_item().item_id,
        receipt=_receipt(),
    )


def _process_response(
    status: str = "SUCCEEDED",
) -> CitationDocumentProcessResponse:
    receipt = _receipt()
    succeeded = status == "SUCCEEDED"
    link = CitationSourceDocumentLinkResponse(
        creating_request_id="citation-source-document-link-request:sha256:"
        + "e" * 64,
        prior_projection_id=_catalog().projection.projection_id,
        prior_item_id=_item().item_id,
        target_snapshot_id=_item().target_snapshot_id,
        identity_projection_id=_item().identity_projection_id,
        literal_citekey="example2026",
        identity_item_id=_identity_item().item_id,
        requested_identity_id=_identity_item().requested_identity_id,
        source_document=receipt.source_document,
        availability_observation_ids=(
            "citation-source-document-observation:sha256:" + "f" * 64,
        ),
        pre_effect_intent_id="citation-document-ingestion-intent:sha256:"
        + "0" * 64,
        linkage_basis="explicit-upload-for-requested-citation",
        limitations=("not-rights-clearance",),
        link_id="citation-source-document-link:sha256:" + "1" * 64,
    )
    return CitationDocumentProcessResponse(
        request_id="citation-document-ingestion-request:sha256:" + "2" * 64,
        intent_id=link.pre_effect_intent_id,
        link_result_id="citation-source-document-link-result:sha256:"
        + "3" * 64,
        source_document_link=link,
        receipt_id=receipt.receipt_id,
        source_document_descriptor_id=receipt.source_document.descriptor_id,
        document_id="citation-document-" + "4" * 64,
        status=status,
        failure_code=(None if succeeded else "PUBLICATION_INDETERMINATE"),
        extraction_bundle_id=(
            "extraction:sha256:" + "5" * 64 if succeeded else None
        ),
        package_id=("package:sha256:" + "6" * 64 if succeeded else None),
        transcript_projection_id=(
            "document-transcript:sha256:" + "7" * 64 if succeeded else None
        ),
        physical_page_count=(2 if succeeded else None),
        publication_action=("create" if succeeded else None),
        result_id="citation-document-ingestion-result:sha256:" + "8" * 64,
    )


class _Provider:
    uploaded: bytes | None = None
    filename_seen: str | None = None

    def read_catalog(self) -> CitationDocumentCatalogResponse:
        return _catalog()

    def receive_source(
        self,
        item_id: str,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceiptResponse:
        assert item_id == _item().item_id
        assert media_type == "application/pdf"
        self.uploaded = source.read()
        return _receipt()

    def process_private(
        self,
        item_id: str,
        request: CitationDocumentProcessRequest,
    ) -> CitationDocumentProcessResponse:
        assert item_id == _item().item_id
        assert request == _process_request()
        return _process_response()

    def read_transcript_collection(self) -> TranscriptCollectionResponse:
        return TranscriptCollectionResponse(documents=())

    def read_transcript(self, document_id: str) -> TranscriptDocumentResponse:
        raise AssertionError(document_id)


class _MissingProvider(_Provider):
    def receive_source(
        self,
        item_id: str,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceiptResponse:
        del item_id, source, media_type
        raise CitationDocumentNotFound


class _LargeProvider(_Provider):
    def receive_source(
        self,
        item_id: str,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceiptResponse:
        del item_id, source, media_type
        raise CitationDocumentPdfTooLarge


class _ConflictProvider(_Provider):
    def process_private(
        self,
        item_id: str,
        request: CitationDocumentProcessRequest,
    ) -> CitationDocumentProcessResponse:
        del item_id, request
        raise CitationDocumentProjectionConflict


def _client(provider: object | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_citation_documents_router(provider))  # type: ignore[arg-type]
    return TestClient(app)


def test_catalog_preserves_owner_projection_and_orthogonal_states() -> None:
    response = _client(_Provider()).get("/citation-documents")

    assert response.status_code == 200
    payload = response.json()
    item = payload["projection"]["items"][0]
    assert item["bibliography_membership_status"] == "defined"
    assert item["key_resolution_status"] == "resolved"
    assert item["identity_items"][0]["status"] == "accepted-active-canonical"
    assert item["document_status"] == "not-observed"
    assert payload["projection"]["source_gaps"] == []
    assert "path" not in payload["projection"]["source_documents"]


def test_catalog_descriptor_bound_is_distinct_from_custody_limit() -> None:
    source = CitationSourceDocumentResponse(
        source_document_id="external-pdf:sha256:" + "9" * 64,
        sha256="9" * 64,
        byte_size=100_000_000,
        media_type="application/pdf",
        descriptor_id="citation-source-document-descriptor:sha256:" + "8" * 64,
    )

    assert source.byte_size == 100_000_000
    with pytest.raises(ValidationError, match="custody limit"):
        CitationDocumentReceiptResponse(
            source_document=source,
            receipt_id="citation-document-receipt:sha256:" + "7" * 64,
        )


def test_source_upload_ignores_filename_and_returns_immutable_receipt() -> None:
    provider = _Provider()
    response = _client(provider).post(
        f"/citation-documents/{_item().item_id}/source",
        files={
            "source_pdf": (
                "../../private.pdf",
                b"%PDF-1.7\nbody",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == _receipt().model_dump(mode="json")
    assert provider.uploaded == b"%PDF-1.7\nbody"
    assert "private.pdf" not in response.text


def test_source_upload_rejects_multiple_files_before_provider() -> None:
    provider = _Provider()
    response = _client(provider).post(
        f"/citation-documents/{_item().item_id}/source",
        files=[
            ("source_pdf", ("one.pdf", b"%PDF-one", "application/pdf")),
            ("source_pdf", ("two.pdf", b"%PDF-two", "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_INVALID_REQUEST"
    )
    assert "one.pdf" not in response.text
    assert "two.pdf" not in response.text
    assert provider.uploaded is None


def test_source_upload_rejects_an_additional_file_without_leaking_names() -> (
    None
):
    provider = _Provider()
    response = _client(provider).post(
        f"/citation-documents/{_item().item_id}/source",
        files=[
            ("source_pdf", ("source.pdf", b"%PDF-one", "application/pdf")),
            ("attachment", ("secret.txt", b"private", "text/plain")),
        ],
    )

    assert response.status_code == 400
    assert "source.pdf" not in response.text
    assert "secret.txt" not in response.text
    assert provider.uploaded is None


def test_source_upload_rejects_declared_mime_before_provider() -> None:
    response = _client(_Provider()).post(
        f"/citation-documents/{_item().item_id}/source",
        files={"source_pdf": ("source.pdf", b"%PDF-", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_UNSUPPORTED_MEDIA_TYPE"
    )


def test_source_upload_maps_safe_missing_and_limit_errors() -> None:
    missing = _client(_MissingProvider()).post(
        f"/citation-documents/{_item().item_id}/source",
        files={"source_pdf": ("source.pdf", b"%PDF-", "application/pdf")},
    )
    oversized = _client(_LargeProvider()).post(
        f"/citation-documents/{_item().item_id}/source",
        files={"source_pdf": ("source.pdf", b"%PDF-", "application/pdf")},
    )

    assert missing.status_code == 404
    assert (
        missing.json()["detail"]["code"] == "CITATION_DOCUMENT_ITEM_NOT_FOUND"
    )
    assert oversized.status_code == 413
    assert (
        oversized.json()["detail"]["code"] == "CITATION_DOCUMENT_PDF_TOO_LARGE"
    )


def test_process_private_returns_only_a_terminal_owner_result() -> None:
    response = _client(_Provider()).post(
        f"/citation-documents/{_item().item_id}/process-private",
        json=_process_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCEEDED"
    assert response.json()["document_id"].startswith("citation-document-")
    assert not {"queued", "running", "progress", "workflow_id"} & set(
        response.json()
    )


def test_process_private_maps_projection_conflict_without_owner_detail() -> (
    None
):
    response = _client(_ConflictProvider()).post(
        f"/citation-documents/{_item().item_id}/process-private",
        json=_process_request().model_dump(mode="json"),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "CITATION_DOCUMENT_PROJECTION_CONFLICT",
        "detail": (
            "citation-document request conflicts with the current projection"
        ),
    }


def test_indeterminate_result_cannot_claim_transcript_readiness() -> None:
    result = _process_response("INDETERMINATE")

    assert result.failure_code == "PUBLICATION_INDETERMINATE"
    assert result.transcript_projection_id is None
    assert result.physical_page_count is None


def test_router_is_unavailable_without_owner() -> None:
    response = _client(None).get("/citation-documents")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_OWNER_UNAVAILABLE"
    )


def test_upload_openapi_declares_binary_limit_and_terminal_process() -> None:
    app = FastAPI()
    app.include_router(create_citation_documents_router(_Provider()))
    schema = app.openapi()
    upload = schema["paths"]["/citation-documents/{item_id}/source"]["post"]
    process = schema["paths"]["/citation-documents/{item_id}/process-private"][
        "post"
    ]
    upload_schema = upload["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]

    assert upload_schema["$ref"].startswith("#/components/schemas/Body_")
    body_name = upload_schema["$ref"].rsplit("/", 1)[-1]
    file_schema = schema["components"]["schemas"][body_name]["properties"][
        "source_pdf"
    ]
    assert file_schema["type"] == "array"
    assert file_schema["minItems"] == 1
    assert file_schema["maxItems"] == 1
    assert file_schema["items"]["type"] == "string"
    assert file_schema["items"]["contentMediaType"] == (
        "application/octet-stream"
    )
    assert file_schema["x-maximum-bytes"] == 50_000_000
    assert process["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/CitationDocumentProcessResponse"}
