from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any, cast

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.citation_document_models import (
    CitationDocumentProcessRequest,
)
from projectkoios.api.citation_document_owner import (
    ApplicationsCitationDocumentOwner,
)
from projectkoios.api.citation_documents import (
    CitationDocumentProjectionConflict,
    CitationDocumentTranscriptProvider,
)
from projectkoios.api.routers.citation_documents import (
    create_citation_documents_router,
)
from projectkoios.api.routers.transcripts import create_transcripts_router
from projectkoios.api.transcripts import TranscriptNotFound
from projectkoios.applications.pdf_corpus_ingestion import (
    CitationDocumentIngestionIntent,
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
    assert item.technical_ingestion_status == "NOT_REQUESTED"
    assert item.technical_ingestion_statuses == ("NOT_REQUESTED",)
    assert item.transcript_status == "NOT_AVAILABLE"
    assert item.allowed_actions == ("PROVIDE_PDF",)
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
    forged_receipt = receipt.model_copy(
        update={"receipt_id": "SECRET-forged-receipt"}
    )
    forged_request = request.model_copy(update={"receipt": forged_receipt})
    citation_app = FastAPI()
    citation_app.include_router(create_citation_documents_router(owner))
    forged_response = TestClient(citation_app).post(
        f"/citation-documents/{item.item_id}/process-private",
        json=forged_request.model_dump(mode="json"),
    )
    assert forged_response.status_code == 400
    assert "SECRET" not in forged_response.text

    result = owner.process_private(str(item.item_id), request)
    replayed = owner.process_private(str(item.item_id), request)

    assert item.document_status == "not-observed"
    assert result.status == "SUCCEEDED"
    assert replayed == result
    assert result.transcript_projection_id is not None

    updated = owner.read_catalog().projection.items[0]
    assert updated.document_status == "available-linked"
    assert updated.private_receipt_status == "RECEIVED"
    assert updated.private_processing_admission_status == "AUTHORIZED"
    assert updated.technical_ingestion_status == "SUCCEEDED"
    assert updated.technical_ingestion_statuses == ("SUCCEEDED",)
    assert updated.transcript_status == "AUTOMATED_UNREVIEWED"
    assert updated.transcript_document_id == result.document_id
    assert updated.search_indexing_status == "NOT_EVALUATED"
    assert updated.human_scientific_acceptance_status == "NOT_EVALUATED"
    assert updated.allowed_actions == ("OPEN_TRANSCRIPT",)
    with pytest.raises(CitationDocumentProjectionConflict):
        owner.receive_source(
            str(item.item_id),
            io.BytesIO(_pdf("Disallowed replacement")),
            media_type="application/pdf",
        )
    replacement_response = TestClient(citation_app).post(
        f"/citation-documents/{item.item_id}/source",
        content=_pdf("Different disallowed replacement"),
        headers={"content-type": "application/pdf"},
    )
    assert replacement_response.status_code == 409
    assert replacement_response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_PROJECTION_CONFLICT"
    )

    reloaded_custody = PrivatePdfCustody(custody.root)
    reloaded_service = CitationDocumentIngestionService(
        custody=reloaded_custody,
        package_root=service.package_root,
        registry=CitationDocumentRegistry(registry.root),
    )
    reloaded_owner = ApplicationsCitationDocumentOwner(
        projection_result=projection,  # type: ignore[arg-type]
        custody=reloaded_custody,
        service=reloaded_service,
        local_processing_authority_assertion_id=(
            "local-operator-configuration:sha256:" + "a" * 64
        ),
        local_processing_admission_decision_id=(
            "private-processing-admission:sha256:" + "b" * 64
        ),
    )
    assert reloaded_owner.read_catalog() == owner.read_catalog()

    transcript = reloaded_owner.read_transcript(str(result.document_id))
    assert transcript.document_id == result.document_id
    assert transcript.status == "AUTOMATED_UNREVIEWED"
    assert "Exact private citation transcript" in transcript.pages[0].text
    assert reloaded_owner.read_transcript_collection().documents[
        0
    ].document_id == (result.document_id)

    app = FastAPI()
    app.include_router(
        create_transcripts_router(
            CitationDocumentTranscriptProvider(reloaded_owner)
        )
    )
    response = TestClient(app).get(f"/transcripts/{result.document_id}")
    assert response.status_code == 200
    assert response.json() == transcript.model_dump(mode="json")

    record_path = next(registry.root.path.iterdir())
    record = record_path.read_bytes()
    stale_link_id = b"citation-source-document-link:sha256:" + b"0" * 64
    assert result.source_document_link.link_id.encode() in record
    record_path.write_bytes(
        record.replace(
            result.source_document_link.link_id.encode(),
            stale_link_id,
        )
    )
    os.chmod(record_path, 0o600)
    stale_response = TestClient(citation_app).get("/citation-documents")
    assert stale_response.status_code == 503
    assert stale_response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_OWNER_UNAVAILABLE"
    )
    assert result.source_document_link.link_id not in stale_response.text


@pytest.mark.parametrize(
    ("expected_status", "failure_mode"),
    (("FAILED", "extract"), ("INDETERMINATE", "publish")),
)
def test_retained_non_success_denies_transcript_after_reload(
    tmp_path: Path,
    expected_status: str,
    failure_mode: str,
) -> None:
    def failed_extractor(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("private extractor detail")

    def indeterminate_publisher(
        package: Any,
        *,
        output_root: AuthorizedRoot,
    ) -> object:
        output_root.child_path(package.document_key).mkdir(mode=0o700)
        raise RuntimeError("private publisher detail")

    projection = _projection()
    custody = PrivatePdfCustody.create(tmp_path / "custody")
    registry = CitationDocumentRegistry(
        _root(tmp_path / "registry", "registry")
    )
    service_arguments: dict[str, object] = {}
    if failure_mode == "extract":
        service_arguments["extractor"] = failed_extractor
    else:
        service_arguments["package_publisher"] = indeterminate_publisher
    service = CitationDocumentIngestionService(
        custody=custody,
        package_root=_root(tmp_path / "packages", "packages"),
        registry=registry,
        **service_arguments,  # type: ignore[arg-type]
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
    receipt = owner.receive_source(
        str(item.item_id),
        io.BytesIO(_pdf("Terminal private citation transcript")),
        media_type="application/pdf",
    )
    result = owner.process_private(
        str(item.item_id),
        CitationDocumentProcessRequest(
            expected_projection_id=catalog.projection.projection_id,
            identity_item_id=item.identity_items[0].item_id,
            receipt=receipt,
        ),
    )

    assert result.status == expected_status
    assert result.transcript_projection_id is None
    reloaded_custody = PrivatePdfCustody(custody.root)
    reloaded_owner = ApplicationsCitationDocumentOwner(
        projection_result=projection,  # type: ignore[arg-type]
        custody=reloaded_custody,
        service=CitationDocumentIngestionService(
            custody=reloaded_custody,
            package_root=service.package_root,
            registry=CitationDocumentRegistry(registry.root),
        ),
        local_processing_authority_assertion_id=(
            "local-operator-configuration:sha256:" + "a" * 64
        ),
        local_processing_admission_decision_id=(
            "private-processing-admission:sha256:" + "b" * 64
        ),
    )
    reloaded = reloaded_owner.read_catalog().projection.items[0]
    assert reloaded.technical_ingestion_status == expected_status
    assert reloaded.technical_ingestion_statuses == (expected_status,)
    assert reloaded.transcript_status == "NOT_AVAILABLE"
    assert reloaded.transcript_document_id is None
    assert reloaded.allowed_actions == ()
    with pytest.raises(TranscriptNotFound):
        reloaded_owner.read_transcript(str(result.document_id))

    if failure_mode == "extract":
        second_owner_receipt = owner.custody.receive(
            io.BytesIO(_pdf("Competing failed private citation")),
            media_type="application/pdf",
        )
        base_item = owner._missing_item(str(item.item_id))
        second_projection = owner._projection_with_receipt(
            base_item,
            second_owner_receipt,
        )
        second_projection_item = second_projection.projection.items[0]
        second_intent = CitationDocumentIngestionIntent(
            receipt=second_owner_receipt,
            projection_result=second_projection,
            projection_item_id=second_projection_item.item_id,
            identity_item_id=second_projection_item.identity_items[0].item_id,
            local_processing_authority_assertion_id=(
                owner.local_processing_authority_assertion_id
            ),
            local_processing_admission_decision_id=(
                owner.local_processing_admission_decision_id
            ),
            extraction_configuration=owner.extraction_configuration,
            artifact_limits=owner.artifact_limits,
        )
        second_request = service.request(second_intent)
        service.package_root.child_path(second_request.document_id).mkdir(
            mode=0o700
        )
        competing_result = service.action(request=second_request)
        assert competing_result.status.value == "INDETERMINATE"
        competing = owner.read_catalog().projection.items[0]
        assert competing.document_status == "ambiguous"
        assert competing.technical_ingestion_status is None
        assert set(competing.technical_ingestion_statuses) == {
            "FAILED",
            "INDETERMINATE",
        }
        assert len(competing.processing_results) == 2
        assert competing.allowed_actions == ()


def test_mutated_custody_root_is_owner_unavailable_not_client_input(
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
    item_id = owner.read_catalog().projection.items[0].item_id
    os.chmod(custody.root.path, 0o755)
    app = FastAPI()
    app.include_router(create_citation_documents_router(owner))

    response = TestClient(app).post(
        f"/citation-documents/{item_id}/source",
        content=b"%PDF-private",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "CITATION_DOCUMENT_OWNER_UNAVAILABLE"
    )
    assert "custody" not in response.text
