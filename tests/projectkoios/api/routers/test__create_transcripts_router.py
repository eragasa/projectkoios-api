from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.provider_errors import ProviderUnavailable
from projectkoios.api.routers.transcripts import create_transcripts_router
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
    TranscriptDocumentSummaryResponse,
    TranscriptPageResponse,
    TranscriptStatus,
)
from projectkoios.api.transcripts import TranscriptNotFound
from pydantic import ValidationError


def _summary() -> TranscriptDocumentSummaryResponse:
    return TranscriptDocumentSummaryResponse(
        document_id=OpaqueId("document-001"),
        display_name="Synthetic materials article",
        status=TranscriptStatus.AUTOMATED_UNREVIEWED,
        physical_page_count=2,
    )


def _document() -> TranscriptDocumentResponse:
    return TranscriptDocumentResponse(
        **_summary().model_dump(),
        pages=(
            TranscriptPageResponse(
                page_id=OpaqueId("page:document-001:0"),
                page_index=0,
                physical_page=1,
                printed_page_label=None,
                text="First page.\n",
            ),
            TranscriptPageResponse(
                page_id=OpaqueId("page:document-001:1"),
                page_index=1,
                physical_page=2,
                printed_page_label="2",
                text="",
            ),
        ),
    )


class _TranscriptFixture:
    def read_collection(self) -> TranscriptCollectionResponse:
        return TranscriptCollectionResponse(documents=(_summary(),))

    def read_document(self, document_id: str) -> TranscriptDocumentResponse:
        if document_id != "document-001":
            raise TranscriptNotFound
        return _document()


class _NotFoundCollection(_TranscriptFixture):
    def read_collection(self) -> TranscriptCollectionResponse:
        raise TranscriptNotFound("private missing detail")


class _UnavailableTranscript(_TranscriptFixture):
    def read_collection(self) -> TranscriptCollectionResponse:
        raise ProviderUnavailable("private root must not escape")


class _InvalidTranscript(_TranscriptFixture):
    def read_collection(self) -> Any:
        return {
            "documents": [
                {
                    **_summary().model_dump(mode="json"),
                    "private_path": "/private/transcript.json",
                }
            ]
        }


class _FailingTranscript(_TranscriptFixture):
    def read_collection(self) -> TranscriptCollectionResponse:
        raise RuntimeError("private provider failure must not escape")


def _client(provider: object | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_transcripts_router(provider))  # type: ignore[arg-type]
    return TestClient(app)


def test__transcripts_router__serves_exact_path_free_projection() -> None:
    client = _client(_TranscriptFixture())

    collection = client.get("/transcripts")
    detail = client.get("/transcripts/document-001")

    assert collection.status_code == 200
    assert collection.json() == {
        "documents": [
            {
                "document_id": "document-001",
                "display_name": "Synthetic materials article",
                "status": "AUTOMATED_UNREVIEWED",
                "physical_page_count": 2,
            }
        ]
    }
    assert detail.status_code == 200
    assert detail.json()["pages"] == [
        {
            "page_id": "page:document-001:0",
            "page_index": 0,
            "physical_page": 1,
            "printed_page_label": None,
            "text": "First page.\n",
        },
        {
            "page_id": "page:document-001:1",
            "page_index": 1,
            "physical_page": 2,
            "printed_page_label": "2",
            "text": "",
        },
    ]
    assert "path" not in detail.text
    assert "artifact" not in detail.text
    assert "sha256" not in detail.text


def test__transcripts_router__allows_an_empty_collection() -> None:
    class EmptyTranscript(_TranscriptFixture):
        def read_collection(self) -> TranscriptCollectionResponse:
            return TranscriptCollectionResponse(documents=())

    response = _client(EmptyTranscript()).get("/transcripts")

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test__transcript_models__require_complete_contiguous_owner_order() -> None:
    payload = _document().model_dump()
    pages = list(payload["pages"])
    pages.reverse()
    payload["pages"] = pages

    with pytest.raises(
        ValidationError,
        match="page indexes must be contiguous and ordered",
    ):
        TranscriptDocumentResponse.model_validate(payload)


def test__transcripts_router__maps_sanitized_provider_boundaries() -> None:
    missing = _client(_TranscriptFixture()).get("/transcripts/missing")
    invalid_collection_error = _client(_NotFoundCollection()).get(
        "/transcripts"
    )
    unavailable = _client(_UnavailableTranscript()).get("/transcripts")
    invalid = _client(_InvalidTranscript()).get("/transcripts")
    unexpected = _client(_FailingTranscript()).get("/transcripts")

    assert missing.status_code == 404
    assert missing.json() == {"detail": "transcript document was not found"}
    assert invalid_collection_error.status_code == 500
    assert invalid_collection_error.json() == {
        "detail": "transcript provider failed unexpectedly"
    }
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": "transcript provider is unavailable"
    }
    assert invalid.status_code == 502
    assert invalid.json() == {
        "detail": "transcript provider returned an invalid projection"
    }
    assert unexpected.status_code == 500
    assert unexpected.json() == {
        "detail": "transcript provider failed unexpectedly"
    }
    responses = (
        missing,
        invalid_collection_error,
        unavailable,
        invalid,
        unexpected,
    )
    combined = " ".join(response.text for response in responses)
    assert "/private" not in combined
    assert "provider failure" not in combined


def test__transcripts_router__is_unavailable_without_provider() -> None:
    client = _client(None)

    responses = [client.get("/transcripts"), client.get("/transcripts/known")]

    assert all(response.status_code == 503 for response in responses)
    assert all(
        response.json() == {"detail": "transcript provider is unavailable"}
        for response in responses
    )


@pytest.mark.parametrize(
    "identifier",
    ["not%20allowed", "a..b", "C:%5Cprivate", "control%00value"],
)
def test__transcripts_router__validates_opaque_document_identity(
    identifier: str,
) -> None:
    response = _client(_TranscriptFixture()).get(f"/transcripts/{identifier}")

    assert response.status_code in {404, 422}
