from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.equation_review import owner as owner_adapter
from projectkoios.api.equation_review.boundary import (
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceStale,
    EquationReviewNoncanonicalLatex,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewQueueMalformed,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review.boundary import (
    EquationReviewEvidenceBinding as ApiEvidenceBinding,
)
from projectkoios.api.equation_review.models import (
    EquationReviewDecisionRequest,
)
from projectkoios.api.equation_review.owner import (
    ApplicationsEquationReviewOwner,
)
from projectkoios.api.equation_review.repository import EquationReviewRepository
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    AssistedEquationAttempt,
    EquationReviewConcurrencyError,
    EquationReviewDisposition,
    EquationReviewEvidenceBinding,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    publish_assisted_equation_attempt,
)
from projectkoios.applications.pdf_corpus_ingestion.equation_review import (
    equation_candidate_artifact_key,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass

_RECORDED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
_LATER_TIME = _RECORDED_AT + timedelta(hours=1)
_REVIEWER_LATEX = r"E = mc^2"
_REVIEWER_SHA256 = hashlib.sha256(_REVIEWER_LATEX.encode()).hexdigest()
_OBSIDIAN_MARKDOWN = "$$\nE = mc^2\n$$"
_OBSIDIAN_SHA256 = hashlib.sha256(_OBSIDIAN_MARKDOWN.encode()).hexdigest()
_REAL_ASSISTANCE_METHOD = (
    "ollama-multimodal-region-processor/1;model=qwen3.5:9b;"
    "model_sha256="
    "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7;"
    "prompt=region-transcription-v1;request=ollama-multimodal-request:sha256:"
    "7ceb7620a8851360d1f585dd5724c20499e4db846d1a1a852a0750d0a4f45bb8;"
    "result=ollama-multimodal-result:sha256:"
    "d7f299517f7c4e67b7137c280143ec0d4d23b7a2db1df5262dad05293141492f"
)


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    page_index: int
    box: tuple[float, float, float, float]
    kind: str = "display"
    evidence_status: str = "proposed"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _stable_id(namespace: str, value: object) -> str:
    return f"{namespace}:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _document_root(
    tmp_path: Path,
    candidates: tuple[_Candidate, ...],
) -> tuple[AuthorizedRoot, dict[str, EquationReviewEvidenceBinding]]:
    document_id = "pizzi2020"
    document = tmp_path / document_id
    source = b"%PDF-1.4\nsynthetic API review queue fixture\n"
    source_sha256 = hashlib.sha256(source).hexdigest()
    detection_id = f"equation-detection-result:sha256:{'d' * 64}"
    extraction_id = f"pdf-extraction-artifact-bundle:sha256:{'e' * 64}"
    files: dict[str, tuple[bytes, str]] = {
        "source/document.pdf": (source, "application/pdf"),
        "source/manifest.json": (
            _canonical(
                {
                    "document_key": document_id,
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
        "content/equations/manifest.json": (
            _canonical({"status": "deterministic-unreviewed"}),
            "application/json",
        ),
    }
    index_records: list[dict[str, object]] = []
    bindings: dict[str, EquationReviewEvidenceBinding] = {}
    for ordinal, specification in enumerate(candidates, start=1):
        key = equation_candidate_artifact_key(specification.candidate_id)
        candidate_root = f"content/equations/regions/{key}"
        image_path = f"{candidate_root}/source/image.png"
        source_path = f"{candidate_root}/source/manifest.json"
        deterministic_path = f"{candidate_root}/deterministic/manifest.json"
        image = b"\x89PNG\r\n\x1a\n" + specification.candidate_id.encode()
        image_sha256 = hashlib.sha256(image).hexdigest()
        region = {
            "content_sha256": image_sha256,
            "page_index": specification.page_index,
            "printed_page_label": str(specification.page_index + 1),
            "source_bounding_box": list(specification.box),
            "source_content_hash": source_sha256,
        }
        source_identity = {
            "candidate_id": specification.candidate_id,
            "document_key": document_id,
            "image_path": image_path,
            "image_sha256": image_sha256,
            "region": region,
            "schema_version": 1,
            "source_sha256": source_sha256,
            "status": "immutable-source-evidence",
        }
        source_manifest = {
            **source_identity,
            "manifest_id": _stable_id(
                "equation-region-source-manifest",
                source_identity,
            ),
        }
        candidate = {
            "candidate_id": specification.candidate_id,
            "confidence": 0.9,
            "configuration_digest": f"configuration:sha256:{ordinal:064x}",
            "detection_input_id": (
                f"equation-detection-input:sha256:{ordinal:064x}"
            ),
            "evidence": [["fixture", "synthetic"]],
            "evidence_status": specification.evidence_status,
            "kind": specification.kind,
            "processor_name": "synthetic-detector",
            "processor_version": "1.0",
            "raw_text": f"E_{{{ordinal}}} = mc^2",
            "rendered_region": region,
            "source_block_id": f"block:{ordinal}",
            "source_label": f"({ordinal})",
            "source_spans": [],
            "warning_ids": [],
        }
        deterministic_identity = {
            "candidate": candidate,
            "detection_result_id": detection_id,
            "document_key": document_id,
            "schema_version": 1,
            "status": "deterministic-proposal",
        }
        deterministic = _canonical(
            {
                **deterministic_identity,
                "manifest_id": _stable_id(
                    "equation-deterministic-manifest",
                    deterministic_identity,
                ),
            }
        )
        files[image_path] = (image, "image/png")
        files[source_path] = (_canonical(source_manifest), "application/json")
        files[deterministic_path] = (deterministic, "application/json")
        index_records.append(
            {
                "candidate_id": specification.candidate_id,
                "deterministic_manifest": deterministic_path,
                "evidence_status": specification.evidence_status,
                "image_path": image_path,
                "image_sha256": image_sha256,
                "kind": specification.kind,
                "source_manifest": source_path,
            }
        )
        bindings[specification.candidate_id] = EquationReviewEvidenceBinding(
            document_id=document_id,
            candidate_id=specification.candidate_id,
            source_sha256=source_sha256,
            candidate_evidence_sha256=hashlib.sha256(deterministic).hexdigest(),
            region_image_sha256=image_sha256,
        )
    files["content/equations/index.json"] = (
        _canonical(
            {
                "candidates": index_records,
                "detection_artifact": (
                    "content/equations/deterministic/detection.json"
                ),
                "detection_result_id": detection_id,
                "document_key": document_id,
                "schema_version": 1,
                "source_sha256": source_sha256,
                "status": "deterministic-unreviewed",
            }
        ),
        "application/json",
    )
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
        "document_key": document_id,
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
    files["document-manifest.json"] = (
        _canonical(
            {
                **completion_identity,
                "package_id": _stable_id(
                    "document-processing-package",
                    completion_identity,
                ),
            }
        ),
        "application/json",
    )
    for relative, (content, _) in files.items():
        target = document / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return (
        AuthorizedRoot.existing(
            document,
            label="synthetic API review queue package",
            root_alias="synthetic-api-review-queue",
            storage_class=RootStorageClass.LOCAL,
        ),
        bindings,
    )


def _attempt(binding: EquationReviewEvidenceBinding) -> AssistedEquationAttempt:
    return AssistedEquationAttempt.create(
        binding=binding,
        method=_REAL_ASSISTANCE_METHOD,
        proposed_latex=r"E = mc^2",
    )


def _legacy_revision(
    root_path: Path,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
) -> None:
    identity = {
        "assistance_proposal_sha256": proposal_sha256,
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "contract_id": "projectkoios.applications.pdf-corpus-equation-review",
        "disposition": "ACCEPT_TRANSCRIPTION",
        "document_id": binding.document_id,
        "note": "Legacy accepted review.",
        "region_image_sha256": binding.region_image_sha256,
        "revision": 1,
        "schema_version": 2,
        "source_sha256": binding.source_sha256,
    }
    decision_value = {
        **identity,
        "recorded_at_utc": "2026-09-29T12:00:00.000000Z",
        "revision_id": _stable_id("equation-human-revision", identity),
    }
    decision = _canonical(decision_value)
    manifest = {
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
    key = equation_candidate_artifact_key(binding.candidate_id)
    target = (
        root_path / "content/equations/regions" / key / "human/revision-0001"
    )
    target.mkdir(parents=True)
    (target / "decision.json").write_bytes(decision)
    (target / "manifest.json").write_bytes(_canonical(manifest))


def _specifications() -> tuple[_Candidate, ...]:
    return (
        _Candidate("pizzi:eq:assisted", 1, (10, 40, 90, 60)),
        _Candidate("pizzi:eq:rejected", 2, (10, 10, 90, 30)),
        _Candidate("pizzi:eq:unassisted", 0, (50, 30, 100, 50)),
        _Candidate("pizzi:eq:legacy", 0, (10, 10, 80, 20)),
        _Candidate("pizzi:eq:schema3", 0, (20, 30, 70, 40)),
        _Candidate("pizzi:eq:inline", 0, (1, 1, 2, 2), kind="inline"),
        _Candidate(
            "pizzi:eq:ambiguous",
            0,
            (2, 2, 3, 3),
            evidence_status="ambiguous",
        ),
    )


def _configuration(document_root: Path) -> EquationReviewConfiguration:
    return EquationReviewConfiguration(
        pizzi2020=EquationReviewDocumentConfiguration(
            document_root=document_root
        )
    )


def _client(document_root: Path) -> TestClient:
    owner = ApplicationsEquationReviewOwner(
        document_root,
        clock=lambda: _RECORDED_AT,
    )
    repository = EquationReviewRepository(
        _configuration(document_root),
        owner=owner,
    )
    app = FastAPI()
    app.include_router(create_equation_review_router(repository))
    return TestClient(app)


def _acceptance_payload(proposal_sha256: str) -> dict[str, object]:
    latex = r"E = mc^{2}"
    markdown = f"$$\n{latex}\n$$"
    return {
        "disposition": "ACCEPT_TRANSCRIPTION",
        "assistance_proposal_sha256": proposal_sha256,
        "reviewer_latex": latex,
        "display_mode": "DISPLAY",
        "render_confirmation": {
            "renderer_id": "mathjax",
            "renderer_version": "3.2.2",
            "rendered_reviewer_latex_sha256": hashlib.sha256(
                latex.encode()
            ).hexdigest(),
            "rendered_obsidian_markdown_sha256": hashlib.sha256(
                markdown.encode()
            ).hexdigest(),
        },
        "note": "Rendered and accepted.",
        "expected_previous_revision": 0,
    }


def _api_binding(binding: EquationReviewEvidenceBinding) -> ApiEvidenceBinding:
    return ApiEvidenceBinding(
        document_id=binding.document_id,
        candidate_id=binding.candidate_id,
        source_sha256=binding.source_sha256,
        candidate_evidence_sha256=binding.candidate_evidence_sha256,
        region_image_sha256=binding.region_image_sha256,
    )


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
        f"$$\n{reviewer_latex}\n$$"
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


def test__real_owner__projects_mixed_stable_queue_and_schema2_decision(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(tmp_path, _specifications())
    document = tmp_path / "pizzi2020"
    assisted = _attempt(bindings["pizzi:eq:assisted"])
    publish_assisted_equation_attempt(assisted, document_root=root)
    legacy = _attempt(bindings["pizzi:eq:legacy"])
    publish_assisted_equation_attempt(legacy, document_root=root)
    _legacy_revision(
        document, bindings["pizzi:eq:legacy"], legacy.proposal_sha256
    )
    schema3 = _attempt(bindings["pizzi:eq:schema3"])
    publish_assisted_equation_attempt(schema3, document_root=root)
    append_human_equation_revision(
        HumanEquationRevisionRequest(
            binding=bindings["pizzi:eq:rejected"],
            disposition=EquationReviewDisposition.REJECT_CANDIDATE,
            assistance_proposal_sha256=None,
            note="Not an equation.",
            recorded_at_utc=_RECORDED_AT,
            expected_previous_revision=0,
        ),
        document_root=root,
    )

    client = _client(document)
    first = client.get("/equation-reviews", params={"document_id": "pizzi2020"})
    second = client.get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    queue = first.json()
    assert queue["projection_id"] == second.json()["projection_id"]
    assert queue["projection_id"].startswith("equation-review-queue:sha256:")
    assert (queue["total"], queue["decided"], queue["pending"]) == (5, 2, 3)
    assert [item["candidate_id"] for item in queue["items"]] == [
        "pizzi:eq:legacy",
        "pizzi:eq:schema3",
        "pizzi:eq:unassisted",
        "pizzi:eq:assisted",
        "pizzi:eq:rejected",
    ]
    by_id = {item["candidate_id"]: item for item in queue["items"]}
    assert by_id["pizzi:eq:unassisted"]["assistance"]["status"] == (
        "NOT_STARTED"
    )
    assert by_id["pizzi:eq:assisted"]["assistance"] == {
        "status": "AUTOMATED_UNREVIEWED",
        "attempt_id": assisted.attempt_id,
        "method": _REAL_ASSISTANCE_METHOD,
        "proposal_sha256": assisted.proposal_sha256,
        "proposed_latex": r"E = mc^2",
    }
    legacy_decision = by_id["pizzi:eq:legacy"]["decision"]
    assert legacy_decision["schema_version"] == 2
    assert legacy_decision["status"] == "LEGACY_ACCEPTANCE"
    assert legacy_decision["reviewer_latex"] is None
    rejected = by_id["pizzi:eq:rejected"]["decision"]
    assert rejected["status"] == "REJECTED"
    assert rejected["reviewer_latex"] is None
    assert by_id["pizzi:eq:legacy"]["source"]["physical_page"] == 1
    assert by_id["pizzi:eq:legacy"]["region"] == {
        "coordinate_space": "PDF_POINTS",
        "x": 10.0,
        "y": 10.0,
        "width": 70.0,
        "height": 10.0,
        "image_sha256": bindings["pizzi:eq:legacy"].region_image_sha256,
    }
    assert (
        by_id["pizzi:eq:legacy"]["deterministic_evidence"]["raw_text"]
        == "E_{4} = mc^2"
    )
    assert str(document) not in first.text
    assert "manifest.json" not in first.text


@pytest.mark.parametrize(
    "method",
    ("x" * 501, "unsafe\nmethod", "unsafe\u202emethod"),
)
def test__owner__rejects_unsafe_assistance_method_as_malformed_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:assisted", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:assisted"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    projection = owner_adapter.project_equation_review_queue(document_root=root)
    item = projection.items[0]
    malformed = replace(
        projection,
        items=(
            replace(
                item,
                assistance=replace(item.assistance, method=method),
            ),
        ),
    )
    monkeypatch.setattr(
        owner_adapter,
        "project_equation_review_queue",
        lambda *, document_root: malformed,
    )

    with pytest.raises(EquationReviewQueueMalformed):
        ApplicationsEquationReviewOwner(tmp_path / "pizzi2020").queue()


def test__real_owner__serves_region_and_put_reloads_schema3_queue(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(tmp_path, _specifications())
    document = tmp_path / "pizzi2020"
    attempt = _attempt(bindings["pizzi:eq:assisted"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    client = _client(document)
    before = client.get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    ).json()

    region = client.get("/equation-reviews/pizzi:eq:assisted/region")
    decision = client.put(
        "/equation-reviews/pizzi:eq:assisted/decision",
        json=_acceptance_payload(attempt.proposal_sha256),
    )
    reloaded = _client(document).get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )

    assert region.status_code == 200
    assert hashlib.sha256(region.content).hexdigest() == (
        bindings["pizzi:eq:assisted"].region_image_sha256
    )
    assert region.headers["content-type"] == "image/png"
    assert decision.status_code == 200
    stored = decision.json()
    assert stored["schema_version"] == 3
    assert stored["reviewer_latex"] == r"E = mc^{2}"
    assert stored["obsidian_markdown"] == "$$\nE = mc^{2}\n$$"
    assert (
        stored["render_confirmation"]
        == _acceptance_payload(attempt.proposal_sha256)["render_confirmation"]
    )
    assert reloaded.status_code == 200
    queue = reloaded.json()
    assert queue["projection_id"] != before["projection_id"]
    assert (queue["decided"], queue["pending"]) == (1, 4)
    latest = next(
        item
        for item in queue["items"]
        if item["candidate_id"] == "pizzi:eq:assisted"
    )
    assert latest["decision"] == {
        key: value for key, value in stored.items() if key != "candidate_id"
    }
    assert latest["current_revision"] == 1
    assert latest["expected_previous_revision"] == 1


def test__real_owner__canonical_math_body_retry_returns_immutable_receipt(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    times = iter((_RECORDED_AT, _LATER_TIME))
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: next(times),
    )
    binding = _api_binding(bindings["pizzi:eq:one"])
    request = _request(attempt.proposal_sha256)

    created = owner.append(binding, request)
    retried = owner.append(binding, request)

    assert created == retried
    assert retried.recorded_at_utc == _RECORDED_AT
    assert retried.recorded_at_utc != _LATER_TIME
    assert retried.revision == 1
    assert retried.schema_version == 3
    assert retried.status == "ACCEPTED"
    assert retried.reviewer_latex == _REVIEWER_LATEX
    assert retried.reviewer_latex_sha256 == _REVIEWER_SHA256
    assert retried.obsidian_markdown == _OBSIDIAN_MARKDOWN
    assert retried.obsidian_markdown_sha256 == _OBSIDIAN_SHA256


def test__real_owner__appends_schema3_correction_after_legacy_schema2(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:legacy", 0, (1, 2, 3, 4)),),
    )
    binding = bindings["pizzi:eq:legacy"]
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    _legacy_revision(
        tmp_path / "pizzi2020",
        binding,
        attempt.proposal_sha256,
    )
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _LATER_TIME,
    )
    corrected_latex = r"E = mc^{2}"

    corrected = owner.append(
        _api_binding(binding),
        _request(
            attempt.proposal_sha256,
            reviewer_latex=corrected_latex,
            note="Accepted after correction and exact render.",
            expected_previous_revision=1,
        ),
    )

    assert corrected.status == "ACCEPTED"
    assert corrected.schema_version == 3
    assert corrected.revision == 2
    assert corrected.reviewer_latex == corrected_latex
    revision_root = (
        tmp_path
        / "pizzi2020/content/equations/regions"
        / equation_candidate_artifact_key(binding.candidate_id)
        / "human"
    )
    assert (revision_root / "revision-0001/decision.json").is_file()
    assert (
        revision_root / "revision-0002/reviewer-latex.txt"
    ).read_text() == corrected_latex


def test__real_owner__types_stale_proposal_and_evidence(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )
    binding = _api_binding(bindings["pizzi:eq:one"])

    with pytest.raises(EquationReviewEvidenceStale):
        owner.append(binding, _request("f" * 64))
    with pytest.raises(EquationReviewEvidenceStale):
        owner.append(
            replace(binding, candidate_evidence_sha256="e" * 64),
            _request(None, disposition="REJECT_CANDIDATE"),
        )


def test__real_owner__distinguishes_render_staleness_and_post_render_edit(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )
    binding = _api_binding(bindings["pizzi:eq:one"])

    with pytest.raises(EquationReviewRenderStale):
        owner.append(
            binding,
            _request(
                attempt.proposal_sha256,
                rendered_obsidian_markdown_sha256="f" * 64,
            ),
        )
    with pytest.raises(EquationReviewEditAfterRender):
        owner.append(
            binding,
            _request(
                attempt.proposal_sha256,
                reviewer_latex=r"E = mc^{2}",
                rendered_reviewer_latex_sha256=_REVIEWER_SHA256,
            ),
        )


@pytest.mark.parametrize(
    "reviewer_latex",
    (
        " E = mc^2",
        "E = mc^2 ",
        "E\r+1",
        "e\u0301 = 1",
        "$E = mc^2$",
        "$$E = mc^2$$",
    ),
)
def test__real_owner__types_noncanonical_math_body(
    tmp_path: Path,
    reviewer_latex: str,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )

    with pytest.raises(EquationReviewNoncanonicalLatex):
        owner.append(
            _api_binding(bindings["pizzi:eq:one"]),
            _request(
                attempt.proposal_sha256,
                reviewer_latex=reviewer_latex,
            ),
        )


def test__real_owner__rejection_has_no_accepted_content(
    tmp_path: Path,
) -> None:
    _, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )

    rejected = owner.append(
        _api_binding(bindings["pizzi:eq:one"]),
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


def test__real_owner__classifies_append_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )

    def lose_race(request: object, *, document_root: object) -> object:
        raise EquationReviewConcurrencyError("private competing evidence")

    monkeypatch.setattr(
        owner_adapter,
        "append_human_equation_revision",
        lose_race,
    )
    with pytest.raises(EquationReviewConcurrentDecision):
        owner.append(
            _api_binding(bindings["pizzi:eq:one"]),
            _request(None, disposition="REJECT_CANDIDATE"),
        )


def test__real_owner__classifies_stale_or_different_winner(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )
    binding = _api_binding(bindings["pizzi:eq:one"])
    owner.append(binding, _request(attempt.proposal_sha256))

    with pytest.raises(EquationReviewRevisionStale):
        owner.append(
            binding,
            _request(
                attempt.proposal_sha256,
                note="Different decision at the same append position.",
            ),
        )
    with pytest.raises(EquationReviewRevisionStale):
        owner.append(
            binding,
            _request(
                None,
                disposition="REJECT_CANDIDATE",
                expected_previous_revision=2,
            ),
        )


def test__real_owner__classifies_partial_append_output(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    attempt = _attempt(bindings["pizzi:eq:one"])
    publish_assisted_equation_attempt(attempt, document_root=root)
    partial = (
        tmp_path
        / "pizzi2020/content/equations/regions"
        / equation_candidate_artifact_key("pizzi:eq:one")
        / "human/revision-0001"
    )
    partial.mkdir(parents=True)
    (partial / "decision.json").write_text("partial", encoding="utf-8")
    owner = ApplicationsEquationReviewOwner(
        tmp_path / "pizzi2020",
        clock=lambda: _RECORDED_AT,
    )

    with pytest.raises(EquationReviewPartialOutput):
        owner.append(
            _api_binding(bindings["pizzi:eq:one"]),
            _request(attempt.proposal_sha256),
        )


def test__real_owner__rejects_unavailable_root_and_clock_edges(
    tmp_path: Path,
) -> None:
    missing = ApplicationsEquationReviewOwner(
        tmp_path / "missing",
        clock=lambda: _RECORDED_AT,
    )
    with pytest.raises(EquationReviewOwnerUnavailable):
        missing.append(
            ApiEvidenceBinding(
                document_id="pizzi2020",
                candidate_id="pizzi:eq:one",
                source_sha256="a" * 64,
                candidate_evidence_sha256="b" * 64,
                region_image_sha256="c" * 64,
            ),
            _request(None, disposition="REJECT_CANDIDATE"),
        )

    _, bindings = _document_root(
        tmp_path / "clock",
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
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
        owner = ApplicationsEquationReviewOwner(
            tmp_path / "clock/pizzi2020",
            clock=lambda clock=clock: clock,
        )
        with pytest.raises(EquationReviewOwnerUnavailable):
            owner.append(
                _api_binding(bindings["pizzi:eq:one"]),
                _request(None, disposition="REJECT_CANDIDATE"),
            )


def test__real_owner__maps_partial_malformed_and_missing_root(
    tmp_path: Path,
) -> None:
    partial_root, _ = _document_root(
        tmp_path / "partial",
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    key = equation_candidate_artifact_key("pizzi:eq:one")
    partial = (
        tmp_path
        / "partial/pizzi2020/content/equations/regions"
        / key
        / "assisted/attempt-0001"
    )
    partial.mkdir(parents=True)
    (partial / "proposal.txt").write_text("E = mc^2")
    malformed = _client(tmp_path / "partial/pizzi2020").get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )

    incomplete_root, _ = _document_root(
        tmp_path / "incomplete",
        (_Candidate("pizzi:eq:two", 0, (1, 2, 3, 4)),),
    )
    (tmp_path / "incomplete/pizzi2020/source/document.pdf").unlink()
    incomplete = _client(tmp_path / "incomplete/pizzi2020").get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )
    unavailable = _client(tmp_path / "absent").get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )

    assert malformed.status_code == 502
    assert malformed.json()["code"] == "EQUATION_REVIEW_QUEUE_MALFORMED"
    assert incomplete.status_code == 503
    assert incomplete.json()["code"] == "EQUATION_REVIEW_QUEUE_INCOMPLETE"
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "EQUATION_REVIEW_OWNER_UNAVAILABLE"
    assert partial_root and incomplete_root


def test__public_profile__never_registers_configured_equation_routes(
    tmp_path: Path,
) -> None:
    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            deployment_profile=DeploymentProfile.PUBLIC,
            equation_review=_configuration(tmp_path / "not-opened"),
        )
    )

    assert "/equation-reviews" not in app.openapi()["paths"]
    response = TestClient(app).get(
        "/equation-reviews", params={"document_id": "pizzi2020"}
    )
    assert response.status_code == 404
