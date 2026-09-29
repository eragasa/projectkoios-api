from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.provider_boundary import invoke_provider
from projectkoios.api.routers.transcript_review import (
    create_transcript_review_router,
)
from projectkoios.api.transcript_review import TranscriptReviewResource
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewItemResponse,
    TranscriptReviewQueueResponse,
    TranscriptReviewRegionResponse,
)

_SECRET = "provider-secret-must-not-escape"


def _client(provider: object) -> TestClient:
    app = FastAPI()
    app.include_router(create_transcript_review_router(provider))  # type: ignore[arg-type]
    return TestClient(app)


class _RuntimeTranscript:
    def read_queue(self) -> TranscriptReviewQueueResponse:
        raise RuntimeError(_SECRET)

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse:
        raise RuntimeError(f"{_SECRET}:{document_id}")

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        raise RuntimeError(f"{_SECRET}:{document_id}")

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        raise RuntimeError(f"{_SECRET}:{document_id}:{asset_id}")


def test__provider_boundary__does_not_catch_cancellation_or_system_exit() -> (
    None
):
    for exit_error in (asyncio.CancelledError(), SystemExit(2)):
        with pytest.raises(type(exit_error)):
            invoke_provider(lambda error=exit_error: _raise_base(error))


def _raise_base(error: BaseException) -> None:
    raise error


def test__transcript_boundary__maps_runtime_errors_without_detail() -> None:
    client = _client(_RuntimeTranscript())
    responses = [
        client.get("/transcript-reviews"),
        client.get("/transcript-reviews/document-001"),
        client.get("/transcript-reviews/document-001/source"),
        client.get("/transcript-reviews/document-001/assets/preview-001"),
    ]

    assert all(response.status_code == 500 for response in responses)
    assert all(
        response.json()["detail"].endswith("failed unexpectedly")
        for response in responses
    )
    assert all(_SECRET not in response.text for response in responses)


def _summary() -> TranscriptReviewDocumentSummaryResponse:
    return TranscriptReviewDocumentSummaryResponse(
        document_id="document-001",
        display_name="Document",
        source_id="source:001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=1,
        physical_page_count=1,
        total_items=0,
        pending_items=0,
        categories=(),
    )


def _malformed_queue() -> TranscriptReviewQueueResponse:
    summary = _summary().model_copy(update={"source_id": "../private.pdf"})
    return TranscriptReviewQueueResponse.model_construct(
        review_id="review-001",
        title="Review",
        status="AUTOMATED_UNREVIEWED",
        total_documents=1,
        total_items=0,
        pending_items=0,
        documents=(summary,),
    )


def _malformed_document() -> TranscriptReviewDocumentResponse:
    region = TranscriptReviewRegionResponse.model_construct(
        x0=0.0,
        y0=0.0,
        x1=float("nan"),
        y1=1.0,
    )
    item = TranscriptReviewItemResponse.model_construct(
        item_id="item-001",
        category="FIGURE",
        risk="REVIEW_REQUIRED",
        physical_page=1,
        printed_page=None,
        region=region,
        source_text="source",
        predecessor_text=None,
        projected_text=None,
        explanation="explanation",
        flags=(),
        preview_asset_id="preview-001",
        links=(),
    )
    return TranscriptReviewDocumentResponse.model_construct(
        **_summary().model_dump(
            exclude={"total_items", "pending_items", "categories"}
        ),
        total_items=1,
        pending_items=1,
        categories=("FIGURE",),
        manifest_id="manifest:001",
        clean_artifact_id="clean:001",
        source_sha256="a" * 64,
        limitations=(),
        items=(item,),
    )


class _MalformedTranscript:
    def read_queue(self) -> TranscriptReviewQueueResponse:
        return _malformed_queue()

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse:
        return _malformed_document()

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        return TranscriptReviewResource(
            body=b"\x89PNG\r\n\x1a\n",
            media_type="application/pdf",
        )

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        return TranscriptReviewResource(
            body=b"RIFF0000NOPE",
            media_type="image/webp",
        )


def test__transcript_boundary__rejects_all_malformed_output() -> None:
    client = _client(_MalformedTranscript())
    responses = [
        client.get("/transcript-reviews"),
        client.get("/transcript-reviews/document-001"),
        client.get("/transcript-reviews/document-001/source"),
        client.get("/transcript-reviews/document-001/assets/preview-001"),
    ]

    assert all(response.status_code == 502 for response in responses)
    assert all(
        response.json()["detail"].endswith("invalid projection")
        for response in responses
    )
    assert all("private" not in response.text for response in responses)
