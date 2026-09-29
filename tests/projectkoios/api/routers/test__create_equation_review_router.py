from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.config import (
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
)
from projectkoios.api.equation_review.boundary import (
    EquationRegionResource,
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewNoncanonicalLatex,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewQueueIncomplete,
    EquationReviewQueueMalformed,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review.models import (
    DeterministicEquationEvidenceResponse,
    EquationDisplayMode,
    EquationRegionEvidenceResponse,
    EquationReviewCandidateResponse,
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
    EquationReviewQueueResponse,
    EquationReviewStatus,
    EquationSourceIdentityResponse,
    ProposedEquationAssistanceResponse,
    UnassistedEquationProposalResponse,
)
from projectkoios.api.equation_review.repository import EquationReviewRepository
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)

_CANDIDATE = "pizzi:eq:assisted"
_UNASSISTED = "pizzi:eq:unassisted"
_PNG = b"\x89PNG\r\n\x1a\nsynthetic-region"
_IMAGE_SHA = hashlib.sha256(_PNG).hexdigest()
_SOURCE_SHA = "a" * 64
_EVIDENCE_SHA = "b" * 64
_PROPOSAL = r"E = mc^2"
_PROPOSAL_SHA = hashlib.sha256(_PROPOSAL.encode()).hexdigest()
_RECORDED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _native(evidence_sha256: str) -> DeterministicEquationEvidenceResponse:
    return DeterministicEquationEvidenceResponse(
        evidence_sha256=evidence_sha256,
        candidate_sha256="c" * 64,
        raw_text="E = mc^2",
        source_label="(1)",
        confidence=0.95,
        evidence_status="proposed",
        source_block_id="block:1",
        detection_input_id="equation-detection-input:one",
        warning_ids=(),
        processor_name="synthetic-detector",
        processor_version="1.0",
        configuration_digest="configuration:sha256:fixture",
    )


def _candidate(
    candidate_id: str,
    *,
    page_index: int,
    assisted: bool,
    decision: EquationReviewDecision | None = None,
) -> EquationReviewCandidateResponse:
    assistance = (
        ProposedEquationAssistanceResponse(
            status="AUTOMATED_UNREVIEWED",
            attempt_id="equation-assisted-attempt:one",
            method="synthetic-assistance",
            proposal_sha256=_PROPOSAL_SHA,
            proposed_latex=_PROPOSAL,
        )
        if assisted
        else UnassistedEquationProposalResponse(
            status="NOT_STARTED",
            attempt_id=None,
            method=None,
            proposal_sha256=None,
            proposed_latex=None,
        )
    )
    revision = 0 if decision is None else decision.revision
    return EquationReviewCandidateResponse(
        candidate_id=candidate_id,
        source=EquationSourceIdentityResponse(
            document_id="pizzi2020",
            source_sha256=_SOURCE_SHA,
            page_index=page_index,
            physical_page=page_index + 1,
            printed_page_label=str(page_index + 1),
        ),
        region=EquationRegionEvidenceResponse(
            coordinate_space="PDF_POINTS",
            x=10.0,
            y=10.0 + page_index,
            width=80.0,
            height=20.0,
            image_sha256=_IMAGE_SHA,
        ),
        deterministic_evidence=_native(_EVIDENCE_SHA),
        display_mode=EquationDisplayMode.DISPLAY,
        assistance=assistance,
        status=(
            EquationReviewStatus.UNREVIEWED
            if decision is None
            else decision.status
        ),
        current_revision=revision,
        expected_previous_revision=revision,
        decision=decision,
    )


def _queue(
    *,
    decision: EquationReviewDecision | None = None,
    projection: str = "equation-review-queue:initial",
) -> EquationReviewQueueResponse:
    items = (
        _candidate(_CANDIDATE, page_index=0, assisted=True, decision=decision),
        _candidate(_UNASSISTED, page_index=1, assisted=False),
    )
    decided = 0 if decision is None else 1
    return EquationReviewQueueResponse(
        contract_id=(
            "projectkoios.applications.pdf-corpus-equation-review-queue"
        ),
        schema_version=1,
        projection_id=projection,
        package_id="document-processing-package:fixture",
        document_id="pizzi2020",
        source_sha256=_SOURCE_SHA,
        total=2,
        decided=decided,
        pending=2 - decided,
        items=items,
    )


class _Owner:
    def __init__(self) -> None:
        self.current = _queue()
        self.bindings: list[EquationReviewEvidenceBinding] = []
        self.queue_calls = 0

    def queue(self) -> EquationReviewQueueResponse:
        self.queue_calls += 1
        return self.current

    def region(
        self,
        candidate_id: str,
        expected_sha256: str,
    ) -> EquationRegionResource:
        assert candidate_id in {_CANDIDATE, _UNASSISTED}
        assert expected_sha256 == _IMAGE_SHA
        return EquationRegionResource(body=_PNG, media_type="image/png")

    def append(
        self,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse:
        self.bindings.append(binding)
        if (
            request.disposition
            is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
        ):
            assert request.reviewer_latex is not None
            assert request.display_mode is not None
            assert request.render_confirmation is not None
            markdown = f"$$\n{request.reviewer_latex}\n$$"
            decision = EquationReviewDecision(
                status=EquationReviewStatus.ACCEPTED,
                schema_version=3,
                disposition=request.disposition,
                assistance_proposal_sha256=request.assistance_proposal_sha256,
                reviewer_latex=request.reviewer_latex,
                reviewer_latex_sha256=hashlib.sha256(
                    request.reviewer_latex.encode()
                ).hexdigest(),
                obsidian_markdown=markdown,
                obsidian_markdown_sha256=hashlib.sha256(
                    markdown.encode()
                ).hexdigest(),
                display_mode=request.display_mode,
                render_confirmation=request.render_confirmation,
                note=request.note,
                revision=request.expected_previous_revision + 1,
                revision_id="equation-human-revision:one",
                recorded_at_utc=_RECORDED_AT,
            )
        else:
            status = (
                EquationReviewStatus.REJECTED
                if request.disposition
                is EquationReviewDisposition.REJECT_CANDIDATE
                else EquationReviewStatus.REVISION_REQUIRED
            )
            decision = EquationReviewDecision(
                status=status,
                schema_version=3,
                disposition=request.disposition,
                assistance_proposal_sha256=request.assistance_proposal_sha256,
                reviewer_latex=None,
                reviewer_latex_sha256=None,
                obsidian_markdown=None,
                obsidian_markdown_sha256=None,
                display_mode=None,
                render_confirmation=None,
                note=request.note,
                revision=request.expected_previous_revision + 1,
                revision_id="equation-human-revision:one",
                recorded_at_utc=_RECORDED_AT,
            )
        self.current = _queue(
            decision=decision,
            projection="equation-review-queue:refreshed",
        )
        return EquationReviewDecisionResponse(
            candidate_id=_CANDIDATE,
            **decision.model_dump(),
        )


def _client(owner: object | None) -> TestClient:
    repository = EquationReviewRepository(
        EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                document_root=Path("/explicit/unused")
            )
        ),
        owner=owner,  # type: ignore[arg-type]
    )
    app = FastAPI()
    app.include_router(create_equation_review_router(repository))
    return TestClient(app)


def _acceptance_payload() -> dict[str, object]:
    latex = r"E = mc^2"
    markdown = f"$$\n{latex}\n$$"
    return {
        "disposition": "ACCEPT_TRANSCRIPTION",
        "assistance_proposal_sha256": _PROPOSAL_SHA,
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


def test__queue__projects_stable_identity_counts_and_unassisted_state() -> None:
    response = _client(_Owner()).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_id"] == "equation-review-queue:initial"
    assert (body["total"], body["decided"], body["pending"]) == (2, 0, 2)
    assert body["items"][0]["assistance"]["status"] == ("AUTOMATED_UNREVIEWED")
    assert body["items"][1]["assistance"] == {
        "status": "NOT_STARTED",
        "attempt_id": None,
        "method": None,
        "proposal_sha256": None,
        "proposed_latex": None,
    }
    serialized = response.text
    assert "/explicit/unused" not in serialized
    assert "manifest.json" not in serialized


def test__region__returns_exact_content_addressed_png() -> None:
    response = _client(_Owner()).get(f"/equation-reviews/{_CANDIDATE}/region")

    assert response.status_code == 200
    assert response.content == _PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == "inline"
    assert response.headers["x-content-type-options"] == "nosniff"


def test__put__refreshes_owner_queue_before_returning_latest_decision() -> None:
    owner = _Owner()
    response = _client(owner).put(
        f"/equation-reviews/{_CANDIDATE}/decision",
        json=_acceptance_payload(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert owner.queue_calls == 2
    assert owner.current.projection_id == "equation-review-queue:refreshed"
    assert owner.current.decided == 1
    assert owner.bindings == [
        EquationReviewEvidenceBinding(
            document_id="pizzi2020",
            candidate_id=_CANDIDATE,
            source_sha256=_SOURCE_SHA,
            candidate_evidence_sha256=_EVIDENCE_SHA,
            region_image_sha256=_IMAGE_SHA,
        )
    ]


def test__put__rejects_unassisted_acceptance_without_owner_write() -> None:
    owner = _Owner()
    response = _client(owner).put(
        f"/equation-reviews/{_UNASSISTED}/decision",
        json=_acceptance_payload(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EQUATION_REVIEW_PROPOSAL_STALE"
    assert owner.bindings == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            EquationReviewEvidenceStale("owner-secret"),
            409,
            "EQUATION_REVIEW_EVIDENCE_STALE",
        ),
        (
            EquationReviewRevisionStale("owner-secret"),
            409,
            "EQUATION_REVIEW_REVISION_STALE",
        ),
        (
            EquationReviewNoncanonicalLatex("owner-secret"),
            409,
            "EQUATION_REVIEW_REVIEWER_LATEX_NONCANONICAL",
        ),
        (
            EquationReviewRenderStale("owner-secret"),
            409,
            "EQUATION_REVIEW_RENDER_STALE",
        ),
        (
            EquationReviewEditAfterRender("owner-secret"),
            409,
            "EQUATION_REVIEW_EDIT_AFTER_RENDER",
        ),
        (
            EquationReviewConcurrentDecision("owner-secret"),
            409,
            "EQUATION_REVIEW_CONCURRENT_DECISION",
        ),
        (
            EquationReviewPartialOutput("owner-secret"),
            503,
            "EQUATION_REVIEW_PARTIAL_OUTPUT",
        ),
    ],
)
def test__put__maps_typed_owner_failures_without_exception_detail(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    class _FailureOwner(_Owner):
        def append(
            self,
            binding: EquationReviewEvidenceBinding,
            request: EquationReviewDecisionRequest,
        ) -> EquationReviewDecisionResponse:
            raise error

    response = _client(_FailureOwner()).put(
        f"/equation-reviews/{_CANDIDATE}/decision",
        json=_acceptance_payload(),
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert str(error) not in response.text


def test__put__requires_refreshed_latest_queue_state() -> None:
    class _StaleOwner(_Owner):
        def append(
            self,
            binding: EquationReviewEvidenceBinding,
            request: EquationReviewDecisionRequest,
        ) -> EquationReviewDecisionResponse:
            prior = self.current
            response = super().append(binding, request)
            self.current = prior
            return response

    response = _client(_StaleOwner()).put(
        f"/equation-reviews/{_CANDIDATE}/decision",
        json=_acceptance_payload(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "EQUATION_REVIEW_PARTIAL_OUTPUT"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            EquationReviewQueueIncomplete("owner-secret-incomplete"),
            503,
            "EQUATION_REVIEW_QUEUE_INCOMPLETE",
        ),
        (
            EquationReviewQueueMalformed("owner-secret-malformed"),
            502,
            "EQUATION_REVIEW_QUEUE_MALFORMED",
        ),
        (
            EquationReviewOwnerUnavailable("owner-secret-unavailable"),
            503,
            "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        ),
        (
            RuntimeError("owner-secret-unexpected"),
            503,
            "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        ),
    ],
)
def test__queue__maps_typed_owner_failures_without_exception_detail(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    class _FailureOwner(_Owner):
        def queue(self) -> EquationReviewQueueResponse:
            raise error

    response = _client(_FailureOwner()).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert str(error) not in response.text


def test__queue__rejects_malformed_owner_projection_as_fixed_502() -> None:
    class _MalformedOwner(_Owner):
        def queue(self) -> EquationReviewQueueResponse:
            return EquationReviewQueueResponse.model_construct(
                **{
                    **_queue().model_dump(),
                    "pending": 99,
                }
            )

    response = _client(_MalformedOwner()).get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "code": "EQUATION_REVIEW_QUEUE_MALFORMED",
        "detail": "equation review owner queue is malformed",
    }


def test__queue_and_candidate__return_fixed_not_found() -> None:
    client = _client(_Owner())

    unknown_document = client.get(
        "/equation-reviews",
        params={"document_id": "other-document"},
    )
    unknown_candidate = client.get("/equation-reviews/unknown-candidate/region")

    assert unknown_document.status_code == 404
    assert unknown_candidate.status_code == 404
