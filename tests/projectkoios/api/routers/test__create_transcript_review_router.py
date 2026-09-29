from __future__ import annotations

import pytest
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


class _BinaryVariantTranscript(_TranscriptFixture):
    def __init__(
        self,
        *,
        source: TranscriptReviewResource | None = None,
        preview: TranscriptReviewResource | None = None,
    ) -> None:
        self.source = source
        self.preview = preview

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        return self.source or super().read_source(document_id)

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        return self.preview or super().read_preview(document_id, asset_id)


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
    assert source.headers["content-disposition"] == "inline"
    assert source.headers["x-content-type-options"] == "nosniff"
    assert preview.content == b"\x89PNG\r\n\x1a\n"
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["content-disposition"] == "inline"
    assert preview.headers["x-content-type-options"] == "nosniff"
    assert "filename" not in source.headers["content-disposition"]
    assert "filename" not in preview.headers["content-disposition"]
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


def test__transcript_router__uses_declared_absolute_binary_limits() -> None:
    assert transcript_router._MAX_PDF_BYTES == 100_000_000
    assert transcript_router._MAX_PREVIEW_BYTES == 20_000_000


def test__transcript_router__enforces_exact_and_plus_one_binary_limits(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcript_router, "_MAX_PDF_BYTES", 5)
    monkeypatch.setattr(transcript_router, "_MAX_PREVIEW_BYTES", 8)
    exact = _client(
        _BinaryVariantTranscript(
            source=TranscriptReviewResource(
                body=b"%PDF-",
                media_type="application/pdf",
            ),
            preview=TranscriptReviewResource(
                body=b"\x89PNG\r\n\x1a\n",
                media_type="image/png",
            ),
        )
    )
    plus_one = _client(
        _BinaryVariantTranscript(
            source=TranscriptReviewResource(
                body=b"%PDF-x",
                media_type="application/pdf",
            ),
            preview=TranscriptReviewResource(
                body=b"\x89PNG\r\n\x1a\nx",
                media_type="image/png",
            ),
        )
    )

    assert (
        exact.get("/transcript-reviews/document-001/source").status_code == 200
    )
    assert (
        exact.get(
            "/transcript-reviews/document-001/assets/preview-001"
        ).status_code
        == 200
    )
    oversized = [
        plus_one.get("/transcript-reviews/document-001/source"),
        plus_one.get("/transcript-reviews/document-001/assets/preview-001"),
    ]
    assert all(response.status_code == 502 for response in oversized)
    assert transcript_router._MAX_PDF_BYTES == 5
    assert transcript_router._MAX_PREVIEW_BYTES == 8


@pytest.mark.parametrize(
    ("media_type", "body"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\n"),
        ("image/jpeg", b"\xff\xd8\xff"),
        ("image/webp", b"RIFF0000WEBP"),
    ],
)
def test__transcript_router__accepts_only_matching_preview_magic(
    media_type: str,
    body: bytes,
) -> None:
    response = _client(
        _BinaryVariantTranscript(
            preview=TranscriptReviewResource(
                body=body,
                media_type=media_type,
            )
        )
    ).get("/transcript-reviews/document-001/assets/preview-001")

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-type"] == media_type


@pytest.mark.parametrize(
    ("media_type", "body"),
    [
        ("application/pdf", b""),
        ("application/pdf", b"not-a-pdf"),
        ("image/png", b"\xff\xd8\xff"),
        ("image/jpeg", b"\x89PNG\r\n\x1a\n"),
        ("image/webp", b"RIFF0000NOPE"),
        ("application/octet-stream", b"%PDF-"),
    ],
)
def test__transcript_router__rejects_empty_spoofed_or_unknown_binary(
    media_type: str,
    body: bytes,
) -> None:
    is_pdf = media_type == "application/pdf"
    provider = _BinaryVariantTranscript(
        source=(
            TranscriptReviewResource(body=body, media_type=media_type)
            if is_pdf
            else None
        ),
        preview=(
            None
            if is_pdf
            else TranscriptReviewResource(body=body, media_type=media_type)
        ),
    )
    path = (
        "/transcript-reviews/document-001/source"
        if is_pdf
        else "/transcript-reviews/document-001/assets/preview-001"
    )

    response = _client(provider).get(path)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "transcript review provider returned an invalid projection"
    }


@pytest.mark.parametrize(
    "identifier",
    ["not%20allowed", "a..b", "C:%5Cprivate", "control%00value"],
)
def test__transcript_router__validates_opaque_path_identifiers(
    identifier: str,
) -> None:
    response = _client(_TranscriptFixture()).get(
        f"/transcript-reviews/{identifier}"
    )

    assert response.status_code in {404, 422}
