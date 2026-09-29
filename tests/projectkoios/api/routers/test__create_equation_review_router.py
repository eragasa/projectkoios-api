from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.config import (
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
)
from projectkoios.api.equation_review import EquationReviewRepository
from projectkoios.api.equation_review_models import (
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
)
from projectkoios.api.equation_review_owner import (
    EquationReviewConcurrentDecision,
    EquationReviewEvidenceBinding,
    EquationReviewPartialOutput,
    EquationReviewRevisionStale,
)
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)

_REGION_BODY = b"\x89PNG\r\n\x1a\nsynthetic-region"
_REGION_SHA256 = hashlib.sha256(_REGION_BODY).hexdigest()
_PROPOSAL_SHA256 = "b" * 64
_RECORDED_AT = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)


class _DecisionStoreFixture:
    def __init__(
        self,
        *,
        decision: EquationReviewDecision | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.failure = failure
        self.bindings: list[EquationReviewEvidenceBinding] = []
        self.requests: list[EquationReviewDecisionRequest] = []

    def latest(
        self,
        binding: EquationReviewEvidenceBinding,
    ) -> EquationReviewDecision | None:
        self.bindings.append(binding)
        if self.failure is not None:
            raise self.failure
        return self.decision

    def append(
        self,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse:
        self.bindings.append(binding)
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return EquationReviewDecisionResponse(
            candidate_id="pizzi2020:eq:001",
            disposition=request.disposition,
            assistance_proposal_sha256=request.assistance_proposal_sha256,
            note=request.note,
            revision=1,
            updated_at_utc=_RECORDED_AT,
        )


def _bundle() -> dict[str, object]:
    return {
        "schema_version": "1",
        "document_id": "pizzi2020",
        "items": [
            {
                "candidate_id": "pizzi2020:eq:001",
                "source": {
                    "document_id": "pizzi2020",
                    "source_name": "pizzi2020.pdf",
                    "source_sha256": "a" * 64,
                    "physical_page": 3,
                },
                "region": {
                    "coordinate_space": "PDF_POINTS",
                    "x": 10.0,
                    "y": 20.0,
                    "width": 30.0,
                    "height": 40.0,
                    "image_sha256": _REGION_SHA256,
                },
                "deterministic_evidence": {
                    "detector": "synthetic-detector",
                    "detector_version": "1",
                    "evidence_sha256": "c" * 64,
                    "extracted_text": "E = mc^2",
                },
                "assistance": {
                    "status": "PROPOSED",
                    "method": "assisted-transcription-v1",
                    "proposal_sha256": _PROPOSAL_SHA256,
                    "proposed_latex": "E = mc^2",
                },
                "decision": None,
            }
        ],
    }


def _repository(
    tmp_path: Path,
    *,
    bundle: object | None = None,
    region_body: bytes | None = _REGION_BODY,
    decision_store: _DecisionStoreFixture | None = None,
) -> tuple[EquationReviewRepository, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bundle_path = tmp_path / "pizzi2020-equation-review.json"
    bundle_path.write_text(
        json.dumps(_bundle() if bundle is None else bundle),
        encoding="utf-8",
    )
    regions_root = tmp_path / "regions"
    regions_root.mkdir()
    if region_body is not None:
        (regions_root / _REGION_SHA256).write_bytes(region_body)
    document_root = tmp_path / "document"
    document_root.mkdir()
    repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=bundle_path,
                regions_root=regions_root,
                document_root=document_root,
            )
        ),
        decision_store=decision_store or _DecisionStoreFixture(),
    )
    return repository, bundle_path, regions_root


def _client(repository: EquationReviewRepository) -> TestClient:
    app = FastAPI()
    app.include_router(create_equation_review_router(repository))
    return TestClient(app)


def test__equation_review__serves_configured_queue_and_bound_region(
    tmp_path: Path,
) -> None:
    repository, _, _ = _repository(tmp_path)
    client = _client(repository)

    queue = client.get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )
    region = client.get("/equation-reviews/pizzi2020:eq:001/region")

    assert queue.status_code == 200
    assert queue.json() == {
        "document_id": "pizzi2020",
        "total": 1,
        "decided": 0,
        "items": _bundle()["items"],
    }
    assert "schema_version" not in queue.json()
    assert region.status_code == 200
    assert region.content == _REGION_BODY
    assert region.headers["content-type"] == "image/png"
    assert region.headers["content-disposition"] == "inline"
    assert region.headers["x-content-type-options"] == "nosniff"


def test__equation_review__is_controlled_by_explicit_pizzi_configuration() -> (
    None
):
    client = _client(EquationReviewRepository(EquationReviewConfiguration()))

    unavailable = client.get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )
    unknown = client.get(
        "/equation-reviews",
        params={"document_id": "other-document"},
    )

    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "code": "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        "detail": "equation review evidence is unavailable",
    }
    assert unknown.status_code == 404
    assert unknown.json() == {
        "detail": "equation review document was not found"
    }


@pytest.mark.parametrize(
    "bundle_mutation",
    [
        lambda bundle: {**bundle, "document_id": "other-document"},
        lambda bundle: {**bundle, "schema_version": "2"},
        lambda bundle: {
            **bundle,
            "items": [
                {
                    **bundle["items"][0],
                    "decision": {
                        "disposition": "ACCEPT_TRANSCRIPTION",
                        "assistance_proposal_sha256": _PROPOSAL_SHA256,
                        "note": "unowned state",
                        "revision": 1,
                        "updated_at_utc": "2026-09-28T00:00:00Z",
                    },
                }
            ],
        },
    ],
)
def test__equation_review__treats_malformed_or_unowned_artifacts_as_unavailable(
    tmp_path: Path,
    bundle_mutation: object,
) -> None:
    mutated = bundle_mutation(_bundle())  # type: ignore[operator]
    repository, _, _ = _repository(tmp_path, bundle=mutated)

    response = _client(repository).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        "detail": "equation review evidence is unavailable",
    }


def test__equation_review__bounds_queue_owner_projection_amplification(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    original = bundle["items"][0]  # type: ignore[index]
    bundle["items"] = [
        {**original, "candidate_id": f"pizzi2020:eq:{index:03d}"}
        for index in range(257)
    ]
    repository, _, _ = _repository(tmp_path, bundle=bundle)

    response = _client(repository).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "EQUATION_REVIEW_OWNER_UNAVAILABLE"


def test__equation_review__rejects_missing_mismatched_and_symlink_regions(
    tmp_path: Path,
) -> None:
    missing_repository, _, missing_root = _repository(
        tmp_path / "missing",
        region_body=None,
    )
    mismatched_repository, _, _ = _repository(
        tmp_path / "mismatched",
        region_body=b"\x89PNG\r\n\x1a\nwrong-region",
    )
    target = tmp_path / "target.png"
    target.write_bytes(_REGION_BODY)
    symlink_repository, _, symlink_root = _repository(
        tmp_path / "symlink",
        region_body=None,
    )
    (symlink_root / _REGION_SHA256).symlink_to(target)

    responses = [
        _client(missing_repository).get(
            "/equation-reviews/pizzi2020:eq:001/region"
        ),
        _client(mismatched_repository).get(
            "/equation-reviews/pizzi2020:eq:001/region"
        ),
        _client(symlink_repository).get(
            "/equation-reviews/pizzi2020:eq:001/region"
        ),
    ]

    assert not (missing_root / _REGION_SHA256).exists()
    assert all(response.status_code == 503 for response in responses)
    assert all(
        response.json()
        == {
            "code": "EQUATION_REVIEW_OWNER_UNAVAILABLE",
            "detail": "equation review evidence is unavailable",
        }
        for response in responses
    )


def test__equation_review__rejects_symlinked_bundle_and_region_root(
    tmp_path: Path,
) -> None:
    repository, bundle_path, regions_root = _repository(tmp_path / "real")
    bundle_link = tmp_path / "bundle-link.json"
    bundle_link.symlink_to(bundle_path)
    root_link = tmp_path / "regions-link"
    root_link.symlink_to(regions_root, target_is_directory=True)
    bundle_symlink_repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=bundle_link,
                regions_root=regions_root,
                document_root=tmp_path / "real/document",
            )
        ),
        decision_store=_DecisionStoreFixture(),
    )
    root_symlink_repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=bundle_path,
                regions_root=root_link,
                document_root=tmp_path / "real/document",
            )
        ),
        decision_store=_DecisionStoreFixture(),
    )

    queue = _client(bundle_symlink_repository).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )
    region = _client(root_symlink_repository).get(
        "/equation-reviews/pizzi2020:eq:001/region"
    )

    assert queue.status_code == 503
    assert region.status_code == 503


def test__equation_review__decision_is_hash_bound_and_owner_persisted(
    tmp_path: Path,
) -> None:
    repository, bundle_path, regions_root = _repository(tmp_path)
    client = _client(repository)
    before_bundle = bundle_path.read_bytes()
    before_region_names = sorted(path.name for path in regions_root.iterdir())
    binding = repository.decision_binding(
        "pizzi2020:eq:001",
        EquationReviewDecisionRequest(
            disposition="ACCEPT_TRANSCRIPTION",
            assistance_proposal_sha256=_PROPOSAL_SHA256,
            note="Checked against the displayed region.",
            expected_previous_revision=0,
        ),
    )

    unavailable = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": _PROPOSAL_SHA256,
            "note": "Checked against the displayed region.",
            "expected_previous_revision": 0,
        },
    )
    mismatched = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": "d" * 64,
            "note": "This must not bind a different proposal.",
            "expected_previous_revision": 0,
        },
    )

    assert binding.document_id == "pizzi2020"
    assert binding.candidate_id == "pizzi2020:eq:001"
    assert binding.source_sha256 == "a" * 64
    assert binding.candidate_evidence_sha256 == "c" * 64
    assert binding.region_image_sha256 == _REGION_SHA256
    assert unavailable.status_code == 200
    assert unavailable.json() == {
        "candidate_id": "pizzi2020:eq:001",
        "disposition": "ACCEPT_TRANSCRIPTION",
        "assistance_proposal_sha256": _PROPOSAL_SHA256,
        "note": "Checked against the displayed region.",
        "revision": 1,
        "updated_at_utc": "2026-09-29T03:00:00Z",
    }
    assert mismatched.status_code == 409
    assert mismatched.json() == {
        "code": "EQUATION_REVIEW_PROPOSAL_STALE",
        "detail": (
            "equation review proposal does not match candidate evidence"
        ),
    }
    assert bundle_path.read_bytes() == before_bundle
    assert sorted(path.name for path in regions_root.iterdir()) == (
        before_region_names
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "document",
        "pizzi2020-equation-review.json",
        "regions",
    ]


def test__equation_review__semantic_retry_returns_same_winning_receipt(
    tmp_path: Path,
) -> None:
    store = _DecisionStoreFixture()
    repository, _, _ = _repository(tmp_path, decision_store=store)
    client = _client(repository)
    request = {
        "disposition": "ACCEPT_TRANSCRIPTION",
        "assistance_proposal_sha256": _PROPOSAL_SHA256,
        "note": "Checked exact evidence.",
        "expected_previous_revision": 0,
    }

    created = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json=request,
    )
    retried = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json=request,
    )

    assert created.status_code == 200
    assert retried.status_code == 200
    assert created.json() == retried.json()
    assert len(store.requests) == 2


def test__equation_review__cannot_accept_absent_assistance(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    item = dict(bundle["items"][0])  # type: ignore[index]
    item["assistance"] = None
    bundle["items"] = [item]
    repository, _, _ = _repository(tmp_path, bundle=bundle)

    response = _client(repository).put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": _PROPOSAL_SHA256,
            "note": "No displayed proposal exists.",
            "expected_previous_revision": 0,
        },
    )

    assert response.status_code == 409


def test__equation_review__projects_latest_owner_decision_into_queue(
    tmp_path: Path,
) -> None:
    decision = EquationReviewDecision(
        disposition=EquationReviewDisposition.REJECT_CANDIDATE,
        assistance_proposal_sha256=None,
        note="Not an equation.",
        revision=2,
        updated_at_utc=datetime(2026, 9, 29, 2, 0, tzinfo=UTC),
    )
    store = _DecisionStoreFixture(decision=decision)
    repository, _, _ = _repository(tmp_path, decision_store=store)

    response = _client(repository).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == 200
    assert response.json()["decided"] == 1
    assert response.json()["items"][0]["decision"] == {
        "disposition": "REJECT_CANDIDATE",
        "assistance_proposal_sha256": None,
        "note": "Not an equation.",
        "revision": 2,
        "updated_at_utc": "2026-09-29T02:00:00Z",
    }


@pytest.mark.parametrize(
    ("failure", "code", "detail"),
    [
        (
            EquationReviewRevisionStale(),
            "EQUATION_REVIEW_REVISION_STALE",
            "equation review revision is stale",
        ),
        (
            EquationReviewConcurrentDecision(),
            "EQUATION_REVIEW_CONCURRENT_DECISION",
            "a different equation review decision won concurrently",
        ),
    ],
)
def test__equation_review__classifies_stale_and_concurrent_append_conflicts(
    tmp_path: Path,
    failure: Exception,
    code: str,
    detail: str,
) -> None:
    repository, _, _ = _repository(
        tmp_path,
        decision_store=_DecisionStoreFixture(failure=failure),
    )

    response = _client(repository).put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": _PROPOSAL_SHA256,
            "note": "Checked exact evidence.",
            "expected_previous_revision": 0,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"code": code, "detail": detail}


def test__equation_review__classifies_partial_owner_output(
    tmp_path: Path,
) -> None:
    repository, _, _ = _repository(
        tmp_path,
        decision_store=_DecisionStoreFixture(
            failure=EquationReviewPartialOutput()
        ),
    )

    response = _client(repository).put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "REJECT_CANDIDATE",
            "assistance_proposal_sha256": None,
            "note": "Not a candidate.",
            "expected_previous_revision": 0,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "EQUATION_REVIEW_PARTIAL_OUTPUT",
        "detail": "equation review output is partial or malformed",
    }


def test__equation_review__rejects_acceptance_without_proposal_hash(
    tmp_path: Path,
) -> None:
    repository, _, _ = _repository(tmp_path)

    response = _client(repository).put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": None,
            "note": "No proposal binding.",
            "expected_previous_revision": 0,
        },
    )

    assert response.status_code == 422
