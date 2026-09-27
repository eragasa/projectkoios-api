from __future__ import annotations

from datetime import UTC, datetime

import pytest
from projectkoios.api.course_models import CourseCode
from projectkoios.api.organizer_models import (
    OrganizerProposalListResponse,
    OrganizerProposalResponse,
)
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewQueueResponse,
    TranscriptReviewRegionResponse,
)
from pydantic import ValidationError


def _proposal(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "file_id": "1" * 64,
        "root_id": "2" * 64,
        "relative_path": "Courses/ENGR219/example.m",
        "name": "example.m",
        "extension": ".m",
        "byte_size": 128,
        "availability": "local",
        "para_category": "resource",
        "life_domain": "teaching",
        "course_code": "ENGR219",
        "confidence": 0.9,
        "suggested_group": "ENGR219",
        "rationale": "The owner projected a course identity.",
        "model": "fixture",
        "model_digest": "3" * 64,
        "proposed_at": datetime(2026, 9, 27, tzinfo=UTC),
    }
    value.update(overrides)
    return value


def test__course_code__is_a_nominal_validated_string_projection() -> None:
    code = CourseCode("ENGR219")

    assert code.root == "ENGR219"
    assert code.model_dump(mode="json") == "ENGR219"

    with pytest.raises(ValidationError):
        CourseCode("engr219")


def test__organizer_proposal__requires_explicit_course_projection() -> None:
    proposal = OrganizerProposalResponse.model_validate(_proposal())

    assert proposal.course_code == CourseCode("ENGR219")
    assert proposal.model_dump(mode="json")["course_code"] == "ENGR219"

    value = _proposal()
    del value["course_code"]
    with pytest.raises(ValidationError):
        OrganizerProposalResponse.model_validate(value)


def test__organizer_proposal__permits_explicit_unmatched_course() -> None:
    proposal = OrganizerProposalResponse.model_validate(
        _proposal(course_code=None)
    )

    assert proposal.course_code is None


def test__organizer_proposal_page__requires_consistent_completion() -> None:
    with pytest.raises(ValidationError):
        OrganizerProposalListResponse(
            proposals=(OrganizerProposalResponse.model_validate(_proposal()),),
            total=2,
            complete=True,
        )


def test__transcript_queue__requires_consistent_counts() -> None:
    summary = TranscriptReviewDocumentSummaryResponse(
        document_id="document-001",
        display_name="Synthetic article",
        source_id="source:synthetic-001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=1,
        physical_page_count=1,
        total_items=2,
        pending_items=2,
        categories=("CITATION",),
    )

    with pytest.raises(ValidationError):
        TranscriptReviewQueueResponse(
            review_id="synthetic-review",
            title="Synthetic review",
            status="AUTOMATED_UNREVIEWED",
            total_documents=1,
            total_items=1,
            pending_items=1,
            documents=(summary,),
        )


def test__transcript_region__requires_positive_geometry() -> None:
    with pytest.raises(ValidationError):
        TranscriptReviewRegionResponse(x0=10, y0=20, x1=10, y1=30)


def test__control_models__forbid_uncontracted_fields() -> None:
    with pytest.raises(ValidationError):
        OrganizerProposalResponse.model_validate(
            _proposal(browser_match="ENGR219")
        )
