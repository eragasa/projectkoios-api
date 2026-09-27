from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.provider_errors import ProviderUnavailable
from projectkoios.api.routers import transcript_review as transcript_router
from projectkoios.api.routers.transcript_review import (
    create_transcript_review_router,
)
from projectkoios.api.transcript_review import (
    TranscriptReviewNotFound,
    TranscriptReviewResource,
)
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewQueueResponse,
)
from pytest import MonkeyPatch


def _summary() -> TranscriptReviewDocumentSummaryResponse:
    return TranscriptReviewDocumentSummaryResponse(
        document_id="document-001",
        display_name="Synthetic materials article",
        source_id="source:synthetic-001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=2,
        physical_page_count=3,
        total_items=0,
        pending_items=0,
        categories=(),
    )


def _queue() -> TranscriptReviewQueueResponse:
    return TranscriptReviewQueueResponse(
        review_id="synthetic-transcript-review",
        title="Synthetic transcript review",
        status="AUTOMATED_UNREVIEWED",
        total_documents=1,
        total_items=0,
        pending_items=0,
        documents=(_summary(),),
    )


def _document() -> TranscriptReviewDocumentResponse:
    return TranscriptReviewDocumentResponse(
        **_summary().model_dump(),
        manifest_id="manifest:synthetic-001",
        clean_artifact_id="clean:synthetic-001",
        source_sha256="a" * 64,
        limitations=("automated_unreviewed",),
        items=(),
    )


class _TranscriptFixture:
    def read_queue(self) -> TranscriptReviewQueueResponse:
        return _queue()

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse:
        if document_id != "document-001":
            raise TranscriptReviewNotFound
        return _document()

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        if document_id != "document-001":
            raise TranscriptReviewNotFound
        return TranscriptReviewResource(
            body=b"%PDF-1.4\n%%EOF\n",
            media_type="application/pdf",
        )

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        if document_id != "document-001" or asset_id != "preview-001":
            raise TranscriptReviewNotFound
        return TranscriptReviewResource(
            body=b"\x89PNG\r\n\x1a\n",
            media_type="image/png",
        )


class _UnavailableTranscript(_TranscriptFixture):
    def read_queue(self) -> TranscriptReviewQueueResponse:
        raise ProviderUnavailable("private owner detail must not escape")


class _OversizedPreviewTranscript(_TranscriptFixture):
    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        return TranscriptReviewResource(
            body=b"1234",
            media_type="image/png",
        )


def _client(provider: _TranscriptFixture | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_transcript_review_router(provider))
    return TestClient(app)


def test__transcript_router__serves_path_free_owner_projections() -> None:
    client = _client(_TranscriptFixture())

    queue = client.get("/transcript-reviews")
    detail = client.get("/transcript-reviews/document-001")
    source = client.get("/transcript-reviews/document-001/source")
    preview = client.get("/transcript-reviews/document-001/assets/preview-001")

    assert queue.status_code == 200
    assert queue.json()["total_documents"] == 1
    assert detail.status_code == 200
    assert detail.json()["source_sha256"] == "a" * 64
    assert source.content == b"%PDF-1.4\n%%EOF\n"
    assert source.headers["content-type"] == "application/pdf"
    assert preview.content == b"\x89PNG\r\n\x1a\n"
    assert preview.headers["content-type"] == "image/png"
    assert "source_file" not in detail.text
    assert "assets_root" not in detail.text


def test__transcript_router__maps_missing_owner_projections() -> None:
    client = _client(_TranscriptFixture())

    document = client.get("/transcript-reviews/missing")
    source = client.get("/transcript-reviews/missing/source")
    preview = client.get("/transcript-reviews/document-001/assets/missing")

    assert document.status_code == 404
    assert document.json() == {
        "detail": "transcript review document was not found"
    }
    assert source.status_code == 404
    assert source.json() == {"detail": "transcript review source was not found"}
    assert preview.status_code == 404
    assert preview.json() == {"detail": "transcript review asset was not found"}


def test__transcript_router__is_honestly_unavailable_without_owner() -> None:
    client = _client(None)

    responses = [
        client.get("/transcript-reviews"),
        client.get("/transcript-reviews/document-001"),
        client.get("/transcript-reviews/document-001/source"),
        client.get("/transcript-reviews/document-001/assets/preview-001"),
    ]

    assert all(response.status_code == 503 for response in responses)
    assert all(
        response.json()
        == {"detail": "transcript review provider is unavailable"}
        for response in responses
    )


def test__transcript_router__does_not_leak_owner_unavailability() -> None:
    response = _client(_UnavailableTranscript()).get("/transcript-reviews")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "transcript review provider is unavailable"
    }
    assert "private owner detail" not in response.text


def test__transcript_router__rejects_invalid_or_oversized_resources(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcript_router, "_MAX_PREVIEW_BYTES", 3)

    response = _client(_OversizedPreviewTranscript()).get(
        "/transcript-reviews/document-001/assets/preview-001"
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "transcript review provider is unavailable"
    }


def test__transcript_router__validates_opaque_path_identifiers() -> None:
    response = _client(_TranscriptFixture()).get(
        "/transcript-reviews/not%20allowed"
    )

    assert response.status_code == 422
