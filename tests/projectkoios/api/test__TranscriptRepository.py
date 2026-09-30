from __future__ import annotations

from pathlib import Path

import pytest
from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.config import TranscriptConfiguration
from projectkoios.api.transcript_models import (
    TranscriptDocumentResponse,
    TranscriptPageResponse,
    TranscriptStatus,
)
from projectkoios.api.transcripts import (
    TranscriptNotFound,
    TranscriptRepository,
    TranscriptUnavailable,
)


def _document() -> TranscriptDocumentResponse:
    return TranscriptDocumentResponse(
        document_id=OpaqueId("document-001"),
        display_name="Synthetic document",
        status=TranscriptStatus.AUTOMATED_UNREVIEWED,
        physical_page_count=1,
        pages=(
            TranscriptPageResponse(
                page_id=OpaqueId("page:001"),
                page_index=0,
                physical_page=1,
                printed_page_label=None,
                text="Exact text.\n",
            ),
        ),
    )


class _Owner:
    def project_document(self) -> TranscriptDocumentResponse:
        return _document()


def test__transcript_repository__projects_one_configured_document() -> None:
    repository = TranscriptRepository(
        TranscriptConfiguration(document_root=Path("/explicit/root")),
        owner=_Owner(),
    )

    collection = repository.read_collection()
    document = repository.read_document("document-001")

    assert len(collection.documents) == 1
    assert collection.documents[0].model_dump() == document.model_dump(
        exclude={"pages"}
    )


def test__transcript_repository__returns_empty_unconfigured_collection() -> (
    None
):
    repository = TranscriptRepository(TranscriptConfiguration())

    collection = repository.read_collection()

    assert collection.documents == ()
    with pytest.raises(TranscriptNotFound):
        repository.read_document("document-001")


def test__transcript_repository__distinguishes_unknown_opaque_identity() -> (
    None
):
    repository = TranscriptRepository(
        TranscriptConfiguration(document_root=Path("/explicit/root")),
        owner=_Owner(),
    )

    with pytest.raises(TranscriptNotFound):
        repository.read_document("other-document")


def test__transcript_repository__requires_owner_when_configured() -> None:
    repository = TranscriptRepository(
        TranscriptConfiguration(document_root=Path("/explicit/root")),
    )

    with pytest.raises(TranscriptUnavailable):
        repository.read_collection()
