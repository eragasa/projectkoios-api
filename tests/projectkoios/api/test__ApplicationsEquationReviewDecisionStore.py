from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from projectkoios.api import equation_review_owner as owner_adapter
from projectkoios.api.equation_review_models import (
    EquationReviewDecisionRequest,
)
from projectkoios.api.equation_review_owner import (
    ApplicationsEquationReviewDecisionStore,
    EquationReviewConcurrentDecision,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewPartialOutput,
    EquationReviewRevisionStale,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewConcurrencyError as OwnerConcurrencyError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewEvidenceMismatch as OwnerEvidenceMismatch,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewPublicationError as OwnerPublicationError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewStaleRevision as OwnerStaleRevision,
)
from pytest import MonkeyPatch, mark, raises

_FIRST_TIME = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
_LATER_TIME = _FIRST_TIME + timedelta(hours=1)
_PROPOSAL_SHA256 = "b" * 64


def _binding() -> EquationReviewEvidenceBinding:
    return EquationReviewEvidenceBinding(
        document_id="pizzi2020",
        candidate_id="pizzi2020:eq:001",
        source_sha256="a" * 64,
        candidate_evidence_sha256="c" * 64,
        region_image_sha256="d" * 64,
    )


def _request() -> EquationReviewDecisionRequest:
    return EquationReviewDecisionRequest.model_validate(
        {
            "disposition": "ACCEPT_TRANSCRIPTION",
            "assistance_proposal_sha256": _PROPOSAL_SHA256,
            "note": "Checked against exact evidence.",
            "expected_previous_revision": 0,
        }
    )


def test__applications_store__generates_time_and_returns_winning_retry_receipt(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    document_root = tmp_path / "pizzi2020"
    document_root.mkdir()
    times = iter((_FIRST_TIME, _LATER_TIME))
    requests: list[Any] = []
    stored: SimpleNamespace | None = None

    def append(request: Any, *, document_root: object) -> SimpleNamespace:
        nonlocal stored
        requests.append(request)
        assert document_root is not None
        if stored is None:
            stored = SimpleNamespace(
                binding=request.binding,
                disposition=request.disposition,
                assistance_proposal_sha256=(request.assistance_proposal_sha256),
                note=request.note,
                revision=1,
                recorded_at_utc=request.recorded_at_utc,
            )
        return SimpleNamespace(revision=stored)

    monkeypatch.setattr(
        owner_adapter,
        "append_human_equation_revision",
        append,
    )
    store = ApplicationsEquationReviewDecisionStore(
        document_root,
        clock=lambda: next(times),
    )

    created = store.append(_binding(), _request())
    retried = store.append(_binding(), _request())

    assert requests[0].recorded_at_utc == _FIRST_TIME
    assert requests[1].recorded_at_utc == _LATER_TIME
    assert requests[0].expected_previous_revision == 0
    assert requests[1].expected_previous_revision == 0
    assert created == retried
    assert retried.updated_at_utc == _FIRST_TIME
    assert retried.updated_at_utc != requests[1].recorded_at_utc
    assert retried.revision == 1
    assert retried.candidate_id == "pizzi2020:eq:001"
    assert list(document_root.iterdir()) == []


def test__applications_store__projects_latest_stored_revision(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    document_root = tmp_path / "pizzi2020"
    document_root.mkdir()
    revision = SimpleNamespace(
        disposition=SimpleNamespace(value="REJECT_CANDIDATE"),
        assistance_proposal_sha256=None,
        note="Not an equation.",
        revision=3,
        recorded_at_utc=_FIRST_TIME,
    )
    monkeypatch.setattr(
        owner_adapter,
        "load_latest_human_equation_revision",
        lambda binding, *, document_root: revision,
    )
    store = ApplicationsEquationReviewDecisionStore(document_root)

    projected = store.latest(_binding())

    assert projected is not None
    assert projected.revision == 3
    assert projected.updated_at_utc == _FIRST_TIME
    assert projected.disposition.value == "REJECT_CANDIDATE"


@mark.parametrize(
    ("owner_failure", "adapter_failure"),
    [
        (OwnerEvidenceMismatch(), EquationReviewEvidenceStale),
        (OwnerStaleRevision(), EquationReviewRevisionStale),
        (OwnerConcurrencyError(), EquationReviewConcurrentDecision),
        (OwnerPublicationError(), EquationReviewPartialOutput),
    ],
)
def test__applications_store__preserves_owner_failure_classification(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    owner_failure: Exception,
    adapter_failure: type[Exception],
) -> None:
    document_root = tmp_path / "pizzi2020"
    document_root.mkdir()

    def fail(request: object, *, document_root: object) -> None:
        raise owner_failure

    monkeypatch.setattr(
        owner_adapter,
        "append_human_equation_revision",
        fail,
    )
    store = ApplicationsEquationReviewDecisionStore(document_root)

    with raises(adapter_failure):
        store.append(_binding(), _request())
