from __future__ import annotations

import hashlib
import json
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
    EquationReviewDecisionRequest,
)
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)

_REGION_BODY = b"\x89PNG\r\n\x1a\nsynthetic-region"
_REGION_SHA256 = hashlib.sha256(_REGION_BODY).hexdigest()
_PROPOSAL_SHA256 = "b" * 64


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
    repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=bundle_path,
                regions_root=regions_root,
            )
        )
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
        "detail": "equation review evidence is unavailable"
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
        "detail": "equation review evidence is unavailable"
    }


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
        response.json() == {"detail": "equation review evidence is unavailable"}
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
            )
        )
    )
    root_symlink_repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=bundle_path,
                regions_root=root_link,
            )
        )
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


def test__equation_review__decision_is_hash_bound_but_never_persisted(
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
        ),
    )

    unavailable = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": _PROPOSAL_SHA256,
            "note": "Checked against the displayed region.",
        },
    )
    mismatched = client.put(
        "/equation-reviews/pizzi2020:eq:001/decision",
        json={
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": "d" * 64,
            "note": "This must not bind a different proposal.",
        },
    )

    assert binding.document_id == "pizzi2020"
    assert binding.candidate_id == "pizzi2020:eq:001"
    assert binding.source_sha256 == "a" * 64
    assert binding.candidate_evidence_sha256 == "c" * 64
    assert binding.region_image_sha256 == _REGION_SHA256
    assert binding.assistance_proposal_sha256 == _PROPOSAL_SHA256
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": "equation review decision persistence is unavailable"
    }
    assert mismatched.status_code == 409
    assert mismatched.json() == {
        "detail": ("equation review decision does not match candidate evidence")
    }
    assert bundle_path.read_bytes() == before_bundle
    assert sorted(path.name for path in regions_root.iterdir()) == (
        before_region_names
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "pizzi2020-equation-review.json",
        "regions",
    ]


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
        },
    )

    assert response.status_code == 409
