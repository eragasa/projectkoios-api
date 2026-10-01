from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import cast

import pymupdf
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.citation_document_models import (
    CitationDocumentProcessRequest,
)
from projectkoios.api.citation_document_owner import (
    ApplicationsCitationDocumentOwner,
)
from projectkoios.api.citation_documents import (
    CitationDocumentTranscriptProvider,
)
from projectkoios.api.routers.transcripts import create_transcripts_router
from projectkoios.applications.pdf_corpus_ingestion import (
    CitationDocumentIngestionService,
    CitationDocumentRegistry,
    PrivatePdfCustody,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass
from projectkoios.references.bibliography import (
    CitationBibliographyObservationBinding,
)
from projectkoios.references.citation_document import (
    CitationDocumentProjectionRequest,
    CitationDocumentProjector,
    CitationSourceDocumentObservation,
)
from projectkoios.references.citations import (
    CitationContentIdentity,
    CitationSourceLocator,
    CitationTargetBibliographyEntry,
    CitationTargetGroup,
    CitationTargetOccurrence,
    CitationTargetSnapshot,
    CitationTargetSourceGap,
)
from projectkoios.references.identity import (
    ProducerIdentity,
    ReferenceCandidate,
    SourceBibliographyObservation,
    replay_identity_decisions,
)


def _id(prefix: str, label: str) -> str:
    return f"{prefix}:{hashlib.sha256(label.encode()).hexdigest()}"


def _content_identity(content: bytes) -> CitationContentIdentity:
    return CitationContentIdentity(
        algorithm="sha256",
        digest=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
    )


def _projection() -> object:
    key = "paperKey"
    bibliography = b"@article{paperKey}\n"
    source = b"\\cite{paperKey}"
    gap_source = b"\\cite{?}"
    observation = SourceBibliographyObservation.create(
        source_id="api-citation-document-test",
        asserted_source_revision="synthetic-revision",
        source_path="references.bib",
        bibliography_bytes=bibliography,
        entry_index=0,
        observed_citekey=key,
        verbatim_entry=bibliography.decode(),
        parser=ProducerIdentity("synthetic-parser", "1"),
    )
    candidate = ReferenceCandidate.create(
        proposed_citekey=key,
        entry_type="article",
        title="Synthetic article",
        authors=("A. Author",),
        year="2026",
        source_observation_ids=(observation.observation_id,),
        generator=ProducerIdentity("api-citation-document-test", "1"),
    )
    identity_projection = replay_identity_decisions((candidate,), ())
    entry = CitationTargetBibliographyEntry(
        entry_id=_id("citation-entry", "entry"),
        entry_index=0,
        key=key,
        entry_type="article",
        locator=CitationSourceLocator(
            source_path="references.bib",
            source_content_identity=_content_identity(bibliography),
            include_index=0,
            byte_start=0,
            byte_end=len(bibliography),
            line=1,
            column=1,
        ),
        entry_content_identity=_content_identity(bibliography),
    )
    occurrence = CitationTargetOccurrence(
        occurrence_id=_id("citation-occurrence", "occurrence"),
        occurrence_index=0,
        call_index=0,
        key_index=0,
        key=key,
        origin="direct",
        locator=CitationSourceLocator(
            source_path="manuscript/main.tex",
            source_content_identity=_content_identity(source),
            include_index=0,
            byte_start=0,
            byte_end=len(source),
            line=1,
            column=1,
        ),
        bibliography_entry_index=0,
        todo_marker_index=None,
    )
    snapshot = CitationTargetSnapshot(
        snapshot_id=_id("citation-snapshot", "snapshot"),
        bibliography_source_path="references.bib",
        bibliography_content_identity=_content_identity(bibliography),
        occurrences=(occurrence,),
        groups=(
            CitationTargetGroup(
                group_id=_id("citation-group", "group"),
                group_index=0,
                key=key,
                occurrence_indexes=(0,),
                direct_occurrence_count=1,
                generated_occurrence_count=0,
                bibliography_entry_index=0,
            ),
        ),
        bibliography_entries=(entry,),
        source_gaps=(
            CitationTargetSourceGap(
                source_gap_id=_id("citation-gap", "gap"),
                source_gap_index=0,
                locator=CitationSourceLocator(
                    source_path="manuscript/gap.tex",
                    source_content_identity=_content_identity(gap_source),
                    include_index=1,
                    byte_start=0,
                    byte_end=len(gap_source),
                    line=1,
                    column=1,
                ),
                reason="placeholder_identifier",
                placeholder_identifier="?",
            ),
        ),
        missing_keys=(),
        duplicate_keys=(),
        uncited_keys=(),
    )
    return CitationDocumentProjector().project(
        request=CitationDocumentProjectionRequest(
            target_snapshot=snapshot,
            bibliography_bindings=(
                CitationBibliographyObservationBinding(
                    entry=entry,
                    observation=observation,
                ),
            ),
            identity_projection=identity_projection,
            document_observations=(
                CitationSourceDocumentObservation(
                    target_snapshot_id=snapshot.snapshot_id,
                    literal_citekey=key,
                    coverage_status="complete",
                    source_documents=(),
                    inaccessible_evidence_ids=(),
                    evidence_id=_id("citation-document-evidence", "missing"),
                ),
            ),
        )
    )


def _root(path: Path, alias: str) -> AuthorizedRoot:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return AuthorizedRoot.existing(
        path,
        label=alias,
        root_alias=alias,
        storage_class=RootStorageClass.LOCAL,
    )


def _pdf(text: str) -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    page = document.new_page(width=300, height=300)
    page.insert_text((40, 100), text, fontsize=12)
    content = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return cast(bytes, content)


def test_owner_receives_processes_and_resolves_verified_transcript(
    tmp_path: Path,
) -> None:
    projection = _projection()
    custody = PrivatePdfCustody.create(tmp_path / "custody")
    registry = CitationDocumentRegistry(
        _root(tmp_path / "registry", "registry")
    )
    service = CitationDocumentIngestionService(
        custody=custody,
        package_root=_root(tmp_path / "packages", "packages"),
        registry=registry,
    )
    owner = ApplicationsCitationDocumentOwner(
        projection_result=projection,  # type: ignore[arg-type]
        custody=custody,
        service=service,
        local_processing_authority_assertion_id=(
            "local-operator-configuration:sha256:" + "a" * 64
        ),
        local_processing_admission_decision_id=(
            "private-processing-admission:sha256:" + "b" * 64
        ),
    )
    catalog = owner.read_catalog()
    item = catalog.projection.items[0]
    identity_item = item.identity_items[0]
    assert len(catalog.projection.source_gaps) == 1
    assert catalog.projection.source_gaps[0].placeholder_identifier == "?"
    assert catalog.projection.source_gaps[0].reason == "placeholder_identifier"

    pdf_bytes = _pdf("Exact private citation transcript")
    receipt = owner.receive_source(
        str(item.item_id),
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
    )
    assert (
        owner.receive_source(
            str(item.item_id),
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
        )
        == receipt
    )
    request = CitationDocumentProcessRequest(
        expected_projection_id=catalog.projection.projection_id,
        identity_item_id=identity_item.item_id,
        receipt=receipt,
    )
    result = owner.process_private(str(item.item_id), request)
    replayed = owner.process_private(str(item.item_id), request)

    assert item.document_status == "not-observed"
    assert result.status == "SUCCEEDED"
    assert replayed == result
    assert result.transcript_projection_id is not None
    transcript = owner.read_transcript(str(result.document_id))
    assert transcript.document_id == result.document_id
    assert transcript.status == "AUTOMATED_UNREVIEWED"
    assert "Exact private citation transcript" in transcript.pages[0].text
    assert owner.read_transcript_collection().documents[0].document_id == (
        result.document_id
    )

    app = FastAPI()
    app.include_router(
        create_transcripts_router(CitationDocumentTranscriptProvider(owner))
    )
    response = TestClient(app).get(f"/transcripts/{result.document_id}")
    assert response.status_code == 200
    assert response.json() == transcript.model_dump(mode="json")
