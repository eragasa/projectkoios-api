from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api import equation_review_owner as owner_adapter
from projectkoios.api.config import (
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
)
from projectkoios.api.equation_review import EquationReviewRepository
from projectkoios.api.equation_review_boundary import (
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review_models import (
    EquationReviewDecisionRequest,
)
from projectkoios.api.equation_review_owner import (
    ApplicationsEquationReviewDecisionStore,
)
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    AssistedEquationAttempt,
    EquationDisplayMode,
    EquationRenderConfirmation,
    EquationReviewConcurrencyError,
    HumanEquationRevisionRequest,
    publish_assisted_equation_attempt,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewDisposition as OwnerDisposition,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewEvidenceBinding as OwnerEvidenceBinding,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    append_human_equation_revision as owner_append,
)
from projectkoios.applications.pdf_corpus_ingestion.equation_review import (
    equation_candidate_artifact_key,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass

_DOCUMENT = "pizzi2020"
_CANDIDATE = "pizzi2020:eq:001"
_FIRST_TIME = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
_LATER_TIME = _FIRST_TIME + timedelta(hours=1)
_REVIEWER_LATEX = r"E = mc^2"
_REVIEWER_SHA256 = hashlib.sha256(_REVIEWER_LATEX.encode()).hexdigest()
_OBSIDIAN_MARKDOWN = "$$\nE = mc^2\n$$"
_OBSIDIAN_SHA256 = hashlib.sha256(_OBSIDIAN_MARKDOWN.encode()).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_package(
    tmp_path: Path,
) -> tuple[
    Path,
    AuthorizedRoot,
    EquationReviewEvidenceBinding,
    OwnerEvidenceBinding,
    str,
    bytes,
]:
    document = tmp_path / _DOCUMENT
    candidate_key = equation_candidate_artifact_key(_CANDIDATE)
    candidate_root = f"content/equations/regions/{candidate_key}"
    image_path = f"{candidate_root}/source/image.png"
    candidate_source_path = f"{candidate_root}/source/manifest.json"
    deterministic_path = f"{candidate_root}/deterministic/manifest.json"
    source = b"%PDF-1.4\nsynthetic bytes only\n"
    image = b"\x89PNG\r\n\x1a\nsynthetic-region"
    source_sha256 = hashlib.sha256(source).hexdigest()
    image_sha256 = hashlib.sha256(image).hexdigest()
    detection_id = f"equation-detection-result:sha256:{'d' * 64}"
    extraction_id = f"pdf-extraction-artifact-bundle:sha256:{'e' * 64}"
    deterministic = _canonical(
        {
            "candidate": {
                "candidate_id": _CANDIDATE,
                "rendered_region": {"content_sha256": image_sha256},
            },
            "detection_result_id": detection_id,
            "document_key": _DOCUMENT,
            "schema_version": 1,
            "status": "deterministic-proposal",
        }
    )
    evidence_sha256 = hashlib.sha256(deterministic).hexdigest()
    files: dict[str, tuple[bytes, str]] = {
        "source/document.pdf": (source, "application/pdf"),
        "source/manifest.json": (
            _canonical(
                {
                    "document_key": _DOCUMENT,
                    "schema_version": 1,
                    "source_byte_size": len(source),
                    "source_path": "source/document.pdf",
                    "source_sha256": source_sha256,
                    "status": "immutable-source",
                }
            ),
            "application/json",
        ),
        "ingestion/extraction.json": (
            _canonical({"synthetic": True}),
            "application/json",
        ),
        "ingestion/manifest.json": (
            _canonical({"status": "deterministic-complete"}),
            "application/json",
        ),
        "content/equations/deterministic/detection.json": (
            _canonical({"result_id": detection_id}),
            "application/json",
        ),
        image_path: (image, "image/png"),
        candidate_source_path: (
            _canonical(
                {
                    "candidate_id": _CANDIDATE,
                    "document_key": _DOCUMENT,
                    "image_path": image_path,
                    "image_sha256": image_sha256,
                    "schema_version": 1,
                    "source_sha256": source_sha256,
                    "status": "immutable-source-evidence",
                }
            ),
            "application/json",
        ),
        deterministic_path: (deterministic, "application/json"),
        "content/equations/index.json": (
            _canonical(
                {
                    "candidates": [
                        {
                            "candidate_id": _CANDIDATE,
                            "deterministic_manifest": deterministic_path,
                            "evidence_status": "proposed",
                            "image_path": image_path,
                            "image_sha256": image_sha256,
                            "kind": "display",
                            "source_manifest": candidate_source_path,
                        }
                    ],
                    "detection_artifact": (
                        "content/equations/deterministic/detection.json"
                    ),
                    "detection_result_id": detection_id,
                    "document_key": _DOCUMENT,
                    "schema_version": 1,
                    "source_sha256": source_sha256,
                    "status": "deterministic-unreviewed",
                }
            ),
            "application/json",
        ),
        "content/equations/manifest.json": (
            _canonical({"status": "deterministic-unreviewed"}),
            "application/json",
        ),
    }
    inventory = [
        {
            "byte_size": len(content),
            "media_type": media_type,
            "relative_path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, (content, media_type) in files.items()
    ]
    completion_identity = {
        "artifact_files": inventory,
        "contract_id": "projectkoios.applications.pdf-corpus-document-package",
        "document_key": _DOCUMENT,
        "equation_detection_result_id": detection_id,
        "extraction_bundle_id": extraction_id,
        "schema_version": 1,
        "source_byte_size": len(source),
        "source_sha256": source_sha256,
        "stages": {
            "assisted": "not-started",
            "equation_detection": "deterministic-complete",
            "human_review": "not-started",
            "ingestion": "deterministic-complete",
            "transcript": "not-started",
        },
        "status": "deterministic-complete",
    }
    completion = {
        **completion_identity,
        "package_id": (
            "document-processing-package:sha256:"
            f"{hashlib.sha256(_canonical(completion_identity)).hexdigest()}"
        ),
    }
    files["document-manifest.json"] = (
        _canonical(completion),
        "application/json",
    )
    for relative, (content, _) in files.items():
        target = document / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    root = AuthorizedRoot.existing(
        document,
        label="synthetic document package",
        root_alias="synthetic-document-package",
        storage_class=RootStorageClass.LOCAL,
    )
    owner_binding = OwnerEvidenceBinding(
        document_id=_DOCUMENT,
        candidate_id=_CANDIDATE,
        source_sha256=source_sha256,
        candidate_evidence_sha256=evidence_sha256,
        region_image_sha256=image_sha256,
    )
    attempt = AssistedEquationAttempt.create(
        binding=owner_binding,
        method="local-equation-assistance-v1",
        proposed_latex=r"E = mc^2",
    )
    publish_assisted_equation_attempt(attempt, document_root=root)
    binding = EquationReviewEvidenceBinding(
        document_id=_DOCUMENT,
        candidate_id=_CANDIDATE,
        source_sha256=source_sha256,
        candidate_evidence_sha256=evidence_sha256,
        region_image_sha256=image_sha256,
    )
    return (
        document,
        root,
        binding,
        owner_binding,
        attempt.proposal_sha256,
        image,
    )


def _write_legacy_schema2_revision(
    document: Path,
    binding: OwnerEvidenceBinding,
    proposal_sha256: str,
) -> tuple[bytes, bytes]:
    identity = {
        "assistance_proposal_sha256": proposal_sha256,
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "contract_id": ("projectkoios.applications.pdf-corpus-equation-review"),
        "disposition": "ACCEPT_TRANSCRIPTION",
        "document_id": binding.document_id,
        "note": "Legacy schema-2 acceptance requires correction.",
        "region_image_sha256": binding.region_image_sha256,
        "revision": 1,
        "schema_version": 2,
        "source_sha256": binding.source_sha256,
    }
    decision = _canonical(
        {
            **identity,
            "recorded_at_utc": "2026-09-28T12:00:00.000000Z",
            "revision_id": (
                "equation-human-revision:sha256:"
                f"{hashlib.sha256(_canonical(identity)).hexdigest()}"
            ),
        }
    )
    decision_value = json.loads(decision)
    manifest = _canonical(
        {
            **decision_value,
            "artifact_files": [
                {
                    "byte_size": len(decision),
                    "relative_path": "decision.json",
                    "sha256": hashlib.sha256(decision).hexdigest(),
                }
            ],
            "status": "human-reviewed",
        }
    )
    revision_root = (
        document
        / "content/equations/regions"
        / equation_candidate_artifact_key(binding.candidate_id)
        / "human/revision-0001"
    )
    revision_root.mkdir(parents=True)
    (revision_root / "decision.json").write_bytes(decision)
    (revision_root / "manifest.json").write_bytes(manifest)
    return decision, manifest


def _request(
    proposal_sha256: str | None,
    *,
    disposition: str = "ACCEPT_TRANSCRIPTION",
    note: str = "Checked against exact evidence.",
    expected_previous_revision: int = 0,
    reviewer_latex: str = _REVIEWER_LATEX,
    display_mode: str = "DISPLAY",
    rendered_reviewer_latex_sha256: str | None = None,
    rendered_obsidian_markdown_sha256: str | None = None,
) -> EquationReviewDecisionRequest:
    accepting = disposition == "ACCEPT_TRANSCRIPTION"
    obsidian = (
        f"$${chr(10)}{reviewer_latex}{chr(10)}$$"
        if display_mode == "DISPLAY"
        else f"${reviewer_latex}$"
    )
    payload: dict[str, object] = {
        "disposition": disposition,
        "assistance_proposal_sha256": proposal_sha256,
        "reviewer_latex": None,
        "display_mode": None,
        "render_confirmation": None,
        "note": note,
        "expected_previous_revision": expected_previous_revision,
    }
    if accepting:
        payload.update(
            {
                "reviewer_latex": reviewer_latex,
                "display_mode": display_mode,
                "render_confirmation": {
                    "renderer_id": "mathjax",
                    "renderer_version": "3.2.2",
                    "rendered_reviewer_latex_sha256": (
                        rendered_reviewer_latex_sha256
                        or hashlib.sha256(reviewer_latex.encode()).hexdigest()
                    ),
                    "rendered_obsidian_markdown_sha256": (
                        rendered_obsidian_markdown_sha256
                        or hashlib.sha256(obsidian.encode()).hexdigest()
                    ),
                },
            }
        )
    return EquationReviewDecisionRequest.model_validate(payload)


def test__real_schema3_owner__unchanged_proposal_retry_and_latest_receipt(
    tmp_path: Path,
) -> None:
    document, _, binding, _, proposal_sha256, _ = _document_package(tmp_path)
    times = iter((_FIRST_TIME, _LATER_TIME))
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: next(times),
    )
    request = _request(proposal_sha256)

    created = store.append(binding, request)
    retried = store.append(binding, request)
    latest = store.latest(binding)

    assert created == retried
    assert latest is not None
    assert retried.recorded_at_utc == _FIRST_TIME
    assert retried.recorded_at_utc != _LATER_TIME
    assert retried.revision == 1
    assert retried.schema_version == 3
    assert retried.status == "ACCEPTED"
    assert retried.reviewer_latex == _REVIEWER_LATEX
    assert retried.reviewer_latex_sha256 == _REVIEWER_SHA256
    assert retried.obsidian_markdown == _OBSIDIAN_MARKDOWN
    assert retried.obsidian_markdown_sha256 == _OBSIDIAN_SHA256
    assert latest.model_dump() == created.model_dump(exclude={"candidate_id"})


def test__real_owner__loads_schema2_then_appends_schema3_correction(
    tmp_path: Path,
) -> None:
    (
        document,
        _,
        binding,
        owner_binding,
        proposal_sha256,
        _,
    ) = _document_package(tmp_path)
    legacy_decision, legacy_manifest = _write_legacy_schema2_revision(
        document,
        owner_binding,
        proposal_sha256,
    )
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _LATER_TIME,
    )

    legacy = store.latest(binding)
    corrected_latex = r"E = mc^{2}"
    corrected = store.append(
        binding,
        _request(
            proposal_sha256,
            reviewer_latex=corrected_latex,
            note="Accepted after correction and exact render.",
            expected_previous_revision=1,
        ),
    )

    assert legacy is not None
    assert legacy.status == "LEGACY_ACCEPTANCE"
    assert legacy.schema_version == 2
    assert legacy.reviewer_latex is None
    assert legacy.obsidian_markdown is None
    assert corrected.status == "ACCEPTED"
    assert corrected.schema_version == 3
    assert corrected.revision == 2
    assert corrected.reviewer_latex == corrected_latex
    assert (
        corrected.reviewer_latex_sha256
        == hashlib.sha256(corrected_latex.encode()).hexdigest()
    )
    assert corrected.obsidian_markdown == f"$$\n{corrected_latex}\n$$"
    revision_root = (
        document
        / "content/equations/regions"
        / equation_candidate_artifact_key(_CANDIDATE)
        / "human"
    )
    assert (revision_root / "revision-0001/decision.json").read_bytes() == (
        legacy_decision
    )
    assert (revision_root / "revision-0001/manifest.json").read_bytes() == (
        legacy_manifest
    )
    assert (
        revision_root / "revision-0002/reviewer-latex.txt"
    ).read_text() == corrected_latex


def test__real_schema3_owner__rejects_stale_proposal_and_evidence(
    tmp_path: Path,
) -> None:
    document, _, binding, _, _, _ = _document_package(tmp_path)
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )

    with pytest.raises(EquationReviewEvidenceStale):
        store.append(binding, _request("f" * 64))
    with pytest.raises(EquationReviewEvidenceStale):
        store.append(
            replace(binding, candidate_evidence_sha256="e" * 64),
            _request(None, disposition="REJECT_CANDIDATE"),
        )


def test__real_schema3_owner__distinguishes_render_staleness_and_edit(
    tmp_path: Path,
) -> None:
    document, _, binding, _, proposal_sha256, _ = _document_package(tmp_path)
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )

    with pytest.raises(EquationReviewRenderStale):
        store.append(
            binding,
            _request(
                proposal_sha256,
                rendered_obsidian_markdown_sha256="f" * 64,
            ),
        )
    with pytest.raises(EquationReviewEditAfterRender):
        store.append(
            binding,
            _request(
                proposal_sha256,
                reviewer_latex=r"E = mc^{2}",
                rendered_reviewer_latex_sha256=_REVIEWER_SHA256,
            ),
        )
    human_root = (
        document
        / "content/equations/regions"
        / equation_candidate_artifact_key(_CANDIDATE)
        / "human"
    )
    assert not human_root.exists()


def test__real_schema3_owner__rejection_has_no_accepted_content(
    tmp_path: Path,
) -> None:
    document, _, binding, _, _, _ = _document_package(tmp_path)
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )

    rejected = store.append(
        binding,
        _request(None, disposition="REJECT_CANDIDATE"),
    )

    assert rejected.status == "REJECTED"
    assert rejected.schema_version == 3
    assert rejected.reviewer_latex is None
    assert rejected.reviewer_latex_sha256 is None
    assert rejected.obsidian_markdown is None
    assert rejected.obsidian_markdown_sha256 is None
    assert rejected.display_mode is None
    assert rejected.render_confirmation is None


def test__real_schema3_owner__classifies_owner_append_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, binding, _, _, _ = _document_package(tmp_path)
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )

    def lose_race(request: object, *, document_root: object) -> object:
        raise EquationReviewConcurrencyError("private competing evidence")

    monkeypatch.setattr(
        owner_adapter,
        "append_human_equation_revision",
        lose_race,
    )
    with pytest.raises(EquationReviewConcurrentDecision):
        store.append(
            binding,
            _request(None, disposition="REJECT_CANDIDATE"),
        )


def test__real_schema3_owner__classifies_stale_and_different_winner(
    tmp_path: Path,
) -> None:
    document, _, binding, _, proposal_sha256, _ = _document_package(tmp_path)
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )
    store.append(binding, _request(proposal_sha256))

    with pytest.raises(EquationReviewRevisionStale):
        store.append(
            binding,
            _request(
                proposal_sha256,
                note="Different decision at the same append position.",
            ),
        )
    with pytest.raises(EquationReviewRevisionStale):
        store.append(
            binding,
            _request(
                None,
                disposition="REJECT_CANDIDATE",
                expected_previous_revision=2,
            ),
        )


def test__real_schema3_owner__classifies_partial_output(
    tmp_path: Path,
) -> None:
    document, _, binding, _, proposal_sha256, _ = _document_package(tmp_path)
    partial = (
        document
        / "content/equations/regions"
        / equation_candidate_artifact_key(_CANDIDATE)
        / "human/revision-0001"
    )
    partial.mkdir(parents=True)
    (partial / "decision.json").write_text("partial", encoding="utf-8")
    store = ApplicationsEquationReviewDecisionStore(
        document,
        clock=lambda: _FIRST_TIME,
    )

    with pytest.raises(EquationReviewPartialOutput):
        store.append(binding, _request(proposal_sha256))


def test__real_schema3_owner__rejects_unavailable_root_and_clock_edges(
    tmp_path: Path,
) -> None:
    missing = ApplicationsEquationReviewDecisionStore(
        tmp_path / "missing",
        clock=lambda: _FIRST_TIME,
    )
    with pytest.raises(EquationReviewOwnerUnavailable):
        missing.append(
            EquationReviewEvidenceBinding(
                document_id=_DOCUMENT,
                candidate_id=_CANDIDATE,
                source_sha256="a" * 64,
                candidate_evidence_sha256="b" * 64,
                region_image_sha256="c" * 64,
            ),
            _request(None, disposition="REJECT_CANDIDATE"),
        )

    document, _, binding, _, _, _ = _document_package(tmp_path / "clock")
    clocks = (
        datetime(2026, 9, 29, 3, 0),
        datetime(
            2026,
            9,
            29,
            4,
            0,
            tzinfo=timezone(timedelta(hours=1)),
        ),
    )
    for clock in clocks:
        store = ApplicationsEquationReviewDecisionStore(
            document,
            clock=lambda clock=clock: clock,
        )
        with pytest.raises(EquationReviewOwnerUnavailable):
            store.append(
                binding,
                _request(None, disposition="REJECT_CANDIDATE"),
            )
    human = (
        document
        / "content/equations/regions"
        / equation_candidate_artifact_key(_CANDIDATE)
        / "human"
    )
    assert not human.exists()


def _owner_request(
    binding: OwnerEvidenceBinding,
    proposal_sha256: str,
) -> HumanEquationRevisionRequest:
    confirmation = EquationRenderConfirmation.create(
        renderer_id="mathjax",
        renderer_version="3.2.2",
        reviewer_latex=_REVIEWER_LATEX,
        display_mode=EquationDisplayMode.DISPLAY,
    )
    return HumanEquationRevisionRequest(
        binding=binding,
        disposition=OwnerDisposition.ACCEPT_TRANSCRIPTION,
        assistance_proposal_sha256=proposal_sha256,
        reviewer_latex=_REVIEWER_LATEX,
        display_mode=EquationDisplayMode.DISPLAY,
        render_confirmation=confirmation,
        note="Valid owner result before adversarial mutation.",
        recorded_at_utc=_FIRST_TIME,
        expected_previous_revision=0,
    )


def _api_client(
    tmp_path: Path,
    document: Path,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
    image: bytes,
) -> TestClient:
    bundle_path = tmp_path / "equation-review.json"
    regions_root = tmp_path / "api-regions"
    regions_root.mkdir()
    (regions_root / binding.region_image_sha256).write_bytes(image)
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "document_id": _DOCUMENT,
                "items": [
                    {
                        "candidate_id": _CANDIDATE,
                        "source": {
                            "document_id": _DOCUMENT,
                            "source_name": "pizzi2020.pdf",
                            "source_sha256": binding.source_sha256,
                            "physical_page": 1,
                        },
                        "region": {
                            "coordinate_space": "PDF_POINTS",
                            "x": 1.0,
                            "y": 1.0,
                            "width": 10.0,
                            "height": 10.0,
                            "image_sha256": binding.region_image_sha256,
                        },
                        "deterministic_evidence": {
                            "detector": "schema-2-fixture",
                            "detector_version": "1",
                            "evidence_sha256": (
                                binding.candidate_evidence_sha256
                            ),
                            "extracted_text": "E = mc^2",
                        },
                        "display_mode": "DISPLAY",
                        "assistance": {
                            "status": "PROPOSED",
                            "method": "local-equation-assistance-v1",
                            "proposal_sha256": proposal_sha256,
                            "proposed_latex": "E = mc^2",
                            "attempt_id": None,
                            "model_provenance": None,
                        },
                        "decision": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    configuration = EquationReviewConfiguration(
        pizzi2020=EquationReviewDocumentConfiguration(
            bundle_path=bundle_path,
            regions_root=regions_root,
            document_root=document,
        )
    )
    repository = EquationReviewRepository(
        configuration,
        decision_store=ApplicationsEquationReviewDecisionStore(
            document,
            clock=lambda: _LATER_TIME,
        ),
    )
    app = FastAPI()
    app.include_router(create_equation_review_router(repository))
    return TestClient(app)


@pytest.mark.parametrize(
    "malformation",
    (
        "result",
        "revision",
        "revision_id",
        "binding",
        "accepted_content",
        "disposition",
        "time",
    ),
)
def test__http__malformed_owner_receipt_is_typed_partial_without_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformation: str,
) -> None:
    (
        document,
        root,
        binding,
        owner_binding,
        proposal_sha256,
        image,
    ) = _document_package(tmp_path)
    valid = owner_append(
        _owner_request(owner_binding, proposal_sha256),
        document_root=root,
    )
    malformed: object = valid
    if malformation == "result":
        malformed = SimpleNamespace(secret="private owner detail")
    elif malformation == "revision":
        object.__setattr__(valid.revision, "revision", 10_000)
    elif malformation == "revision_id":
        object.__setattr__(
            valid.revision,
            "revision_id",
            f"equation-human-revision:sha256:{'f' * 64}",
        )
    elif malformation == "binding":
        object.__setattr__(
            valid.revision.binding,
            "candidate_id",
            "pizzi2020:eq:other",
        )
    elif malformation == "accepted_content":
        object.__setattr__(
            valid.revision,
            "obsidian_markdown",
            "$$\nsilently different\n$$",
        )
    elif malformation == "disposition":
        object.__setattr__(
            valid.revision,
            "disposition",
            SimpleNamespace(value="private owner detail"),
        )
    else:
        object.__setattr__(
            valid.revision,
            "recorded_at_utc",
            datetime(2026, 9, 29, 3, 0),
        )

    def malformed_append(
        request: object,
        *,
        document_root: object,
    ) -> object:
        return malformed

    monkeypatch.setattr(
        owner_adapter,
        "append_human_equation_revision",
        malformed_append,
    )
    client = _api_client(
        tmp_path,
        document,
        binding,
        proposal_sha256,
        image,
    )

    response = client.put(
        f"/equation-reviews/{_CANDIDATE}/decision",
        json=_request(proposal_sha256).model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "EQUATION_REVIEW_PARTIAL_OUTPUT",
        "detail": "equation review output is partial or malformed",
    }
    assert "private owner detail" not in response.text


def test__http__malformed_owner_latest_is_typed_partial_without_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, binding, _, proposal_sha256, image = _document_package(
        tmp_path
    )
    monkeypatch.setattr(
        owner_adapter,
        "load_latest_human_equation_revision",
        lambda binding, *, document_root: SimpleNamespace(
            secret="private owner latest detail"
        ),
    )
    client = _api_client(
        tmp_path,
        document,
        binding,
        proposal_sha256,
        image,
    )

    response = client.get(
        "/equation-reviews",
        params={"document_id": _DOCUMENT},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "EQUATION_REVIEW_PARTIAL_OUTPUT",
        "detail": "equation review output is partial or malformed",
    }
    assert "private owner latest detail" not in response.text
