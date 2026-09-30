from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from projectkoios.api import transcript_owner as owner_module
from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    OrganizerConfiguration,
    ProjectKoiosAppConfiguration,
    TranscriptConfiguration,
)
from projectkoios.api.provider_boundary import MalformedProviderProjection
from projectkoios.api.transcript_owner import ApplicationsTranscriptOwner
from projectkoios.api.transcripts import TranscriptUnavailable
from projectkoios.applications.pdf_corpus_ingestion import (
    DOCUMENT_TRANSCRIPT_CONTRACT_ID,
    DocumentTranscriptIncompleteError,
    DocumentTranscriptMalformedError,
    DocumentTranscriptPage,
    DocumentTranscriptProjection,
    DocumentTranscriptStatus,
    DocumentTranscriptUnavailableError,
)
from projectkoios.references import AuthorizedRoot
from pytest import MonkeyPatch


def _projection() -> DocumentTranscriptProjection:
    return DocumentTranscriptProjection(
        contract_id=DOCUMENT_TRANSCRIPT_CONTRACT_ID,
        document_id="document-001",
        display_name="Synthetic document",
        status=DocumentTranscriptStatus.AUTOMATED_UNREVIEWED,
        physical_page_count=2,
        pages=(
            DocumentTranscriptPage(
                page_id="page:001:0",
                page_index=0,
                physical_page=1,
                printed_page_label=None,
                text="Exact first page.\n",
            ),
            DocumentTranscriptPage(
                page_id="page:001:1",
                page_index=1,
                physical_page=2,
                printed_page_label="2",
                text="",
            ),
        ),
        source_sha256="a" * 64,
        source_byte_size=100,
        media_type="application/pdf",
        metadata=(("title", "Synthetic document"),),
        extraction_manifest_id="manifest:private-evidence",
        package_id="package:private-evidence",
        projection_id="projection:private-evidence",
    )


def _owner(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    projection: DocumentTranscriptProjection | Exception,
) -> ApplicationsTranscriptOwner:
    document_root = tmp_path / "document"
    document_root.mkdir()

    def project(
        *, document_root: AuthorizedRoot
    ) -> DocumentTranscriptProjection:
        assert isinstance(document_root, AuthorizedRoot)
        if isinstance(projection, Exception):
            raise projection
        return projection

    monkeypatch.setattr(owner_module, "project_document_transcript", project)
    return ApplicationsTranscriptOwner(document_root)


def test__applications_transcript_owner__maps_only_display_fields(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    response = _owner(tmp_path, monkeypatch, _projection()).project_document()

    assert response.model_dump(mode="json") == {
        "document_id": "document-001",
        "display_name": "Synthetic document",
        "status": "AUTOMATED_UNREVIEWED",
        "physical_page_count": 2,
        "pages": [
            {
                "page_id": "page:001:0",
                "page_index": 0,
                "physical_page": 1,
                "printed_page_label": None,
                "text": "Exact first page.\n",
            },
            {
                "page_id": "page:001:1",
                "page_index": 1,
                "physical_page": 2,
                "printed_page_label": "2",
                "text": "",
            },
        ],
    }
    body = response.model_dump_json()
    for forbidden in (
        "source_id",
        "source_sha256",
        "manifest",
        "package",
        "projection",
        "metadata",
        "path",
    ):
        assert forbidden not in body


@pytest.mark.parametrize(
    "owner_error",
    [
        DocumentTranscriptIncompleteError("private incomplete detail"),
        DocumentTranscriptUnavailableError("private unavailable detail"),
    ],
)
def test__applications_transcript_owner__maps_unavailable_failures(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    owner_error: Exception,
) -> None:
    owner = _owner(tmp_path, monkeypatch, owner_error)

    with pytest.raises(TranscriptUnavailable) as caught:
        owner.project_document()

    assert caught.value.__cause__ is owner_error


def test__applications_transcript_owner__maps_malformed_owner_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    owner_error = DocumentTranscriptMalformedError("private malformed detail")
    owner = _owner(tmp_path, monkeypatch, owner_error)

    with pytest.raises(MalformedProviderProjection) as caught:
        owner.project_document()

    assert caught.value.__cause__ is owner_error


def test__applications_transcript_owner__rejects_invalid_projection(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    malformed = replace(
        _projection(),
        pages=(object(),),  # type: ignore[arg-type]
    )
    owner = _owner(tmp_path, monkeypatch, malformed)

    with pytest.raises(MalformedProviderProjection):
        owner.project_document()


def test__applications_transcript_owner__maps_missing_root_to_unavailable(
    tmp_path: Path,
) -> None:
    owner = ApplicationsTranscriptOwner(tmp_path / "missing")

    with pytest.raises(TranscriptUnavailable):
        owner.project_document()


def test__configured_control_app__constructs_transcript_owner_lazily(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private-document-root"
    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            deployment_profile=DeploymentProfile.CONTROL,
            organizer=OrganizerConfiguration(
                catalog_path=tmp_path / "organizer.sqlite3"
            ),
            transcripts=TranscriptConfiguration(document_root=private_root),
        )
    )

    response = TestClient(app).get("/transcripts")

    assert response.status_code == 503
    assert response.json() == {"detail": "transcript provider is unavailable"}
    assert str(private_root) not in response.text


def test__applications_transcript_owner__does_not_hide_unexpected_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    owner_error = RuntimeError("unexpected private failure")
    owner = _owner(tmp_path, monkeypatch, owner_error)

    with pytest.raises(RuntimeError) as caught:
        owner.project_document()

    assert caught.value is owner_error
