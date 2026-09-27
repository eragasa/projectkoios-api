from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from projectkoios.api.boundary_models import (
    MAX_BINARY_SIZE,
    MAX_COUNT,
    MAX_OPAQUE_ID_LENGTH,
    MAX_REGION_COORDINATE,
    OpaqueId,
    SafeRelativePosixPath,
)
from projectkoios.api.course_models import CourseCode, PublicCourseCatalog
from projectkoios.api.organizer_models import (
    OrganizerProposalListResponse,
    OrganizerProposalResponse,
)
from projectkoios.api.project_models import PublicProjectCatalog
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewItemResponse,
    TranscriptReviewLinkResponse,
    TranscriptReviewQueueResponse,
    TranscriptReviewRegionResponse,
)
from pydantic import TypeAdapter, ValidationError


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


def test__opaque_ids__enforce_exact_length_and_reject_path_syntax() -> None:
    assert len(OpaqueId("a" * MAX_OPAQUE_ID_LENGTH)) == 256

    for value in (
        "a" * (MAX_OPAQUE_ID_LENGTH + 1),
        "/absolute",
        "../traversal",
        "segment/child",
        r"segment\\child",
        "a..b",
        "C:private",
        "control\x00value",
    ):
        with pytest.raises(ValidationError):
            TranscriptReviewDocumentSummaryResponse(
                document_id="document-001",
                display_name="Document",
                source_id=value,
                status="AUTOMATED_UNREVIEWED",
                artifact_generation=1,
                physical_page_count=1,
                total_items=0,
                pending_items=0,
                categories=(),
            )


def test__organizer_paths__are_normalized_relative_posix_display_paths() -> (
    None
):
    exact = "a" * 4096
    assert SafeRelativePosixPath(exact) == exact

    adapter = TypeAdapter(SafeRelativePosixPath)
    for value in (
        "a" * 4097,
        "/absolute",
        "../traversal",
        "a/../b",
        "a/./b",
        "a//b",
        "a/",
        r"a\\b",
        "a\x00b",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


def test__organizer_numeric_bounds_are_exact_and_finite() -> None:
    assert (
        OrganizerProposalResponse.model_validate(
            _proposal(byte_size=MAX_BINARY_SIZE, confidence=1.0)
        ).byte_size
        == MAX_BINARY_SIZE
    )

    for override in (
        {"byte_size": MAX_BINARY_SIZE + 1},
        {"confidence": float("nan")},
        {"confidence": float("inf")},
    ):
        with pytest.raises(ValidationError):
            OrganizerProposalResponse.model_validate(_proposal(**override))


def test__organizer_proposal_page__rejects_duplicate_identities() -> None:
    proposal = OrganizerProposalResponse.model_validate(_proposal())

    with pytest.raises(ValidationError):
        OrganizerProposalListResponse(
            proposals=(proposal, proposal),
            total=2,
            complete=True,
        )


def test__organizer_proposal_count__accepts_limit_rejects_plus_one() -> None:
    proposals = tuple(
        OrganizerProposalResponse.model_validate(
            _proposal(
                file_id=f"{index:064x}",
                relative_path=f"Courses/{index}.m",
                name=f"{index}.m",
            )
        )
        for index in range(500)
    )
    page = OrganizerProposalListResponse(
        proposals=proposals,
        total=500,
        complete=True,
    )
    assert len(page.proposals) == 500

    with pytest.raises(ValidationError):
        OrganizerProposalListResponse(
            proposals=proposals + (proposals[0],),
            total=501,
            complete=True,
        )


def test__transcript_regions__reject_invalid_coordinates() -> None:
    region = TranscriptReviewRegionResponse(
        x0=0,
        y0=0,
        x1=MAX_REGION_COORDINATE,
        y1=MAX_REGION_COORDINATE,
    )
    assert region.x1 == MAX_REGION_COORDINATE

    for coordinate in (
        float("nan"),
        float("inf"),
        MAX_REGION_COORDINATE + 1,
    ):
        with pytest.raises(ValidationError):
            TranscriptReviewRegionResponse(
                x0=0,
                y0=0,
                x1=coordinate,
                y1=1,
            )


def _item(
    item_id: str,
    *,
    target_item_id: str | None = None,
) -> TranscriptReviewItemResponse:
    links = (
        (
            TranscriptReviewLinkResponse(
                relation="CITES",
                resolution="LINKED",
                target_item_id=target_item_id,
                label="Linked item",
            ),
        )
        if target_item_id is not None
        else ()
    )
    return TranscriptReviewItemResponse(
        item_id=item_id,
        category="CITATION",
        risk="REVIEW_REQUIRED",
        physical_page=1,
        source_text="source",
        explanation="explanation",
        links=links,
    )


def _document(
    items: tuple[TranscriptReviewItemResponse, ...],
) -> TranscriptReviewDocumentResponse:
    return TranscriptReviewDocumentResponse(
        document_id="document-001",
        display_name="Document",
        source_id="source:001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=1,
        physical_page_count=1,
        total_items=len(items),
        pending_items=len(items),
        categories=(("CITATION",) if items else ()),
        manifest_id="manifest:001",
        clean_artifact_id="artifact:001",
        source_sha256="a" * 64,
        limitations=(),
        items=items,
    )


@pytest.mark.parametrize(
    "field",
    ["source_id", "manifest_id", "clean_artifact_id"],
)
@pytest.mark.parametrize(
    "invalid_id",
    ["/absolute", "../traversal", r"path\\value", "x" * 257],
)
def test__transcript_artifact_ids__reject_path_like_values(
    field: str,
    invalid_id: str,
) -> None:
    payload = _document(()).model_dump()
    payload[field] = invalid_id

    with pytest.raises(ValidationError):
        TranscriptReviewDocumentResponse.model_validate(payload)


def test__transcript_documents__require_unique_consistent_item_links() -> None:
    first = _item("item-001", target_item_id="item-002")
    second = _item("item-002")
    assert _document((first, second)).total_items == 2

    for items in (
        (_item("item-001"), _item("item-001")),
        (_item("item-001", target_item_id="missing"),),
        (_item("item-001", target_item_id="item-001"),),
    ):
        with pytest.raises(ValidationError):
            _document(items)


def test__transcript_links__require_target_only_for_linked_resolution() -> None:
    for resolution, target in (
        ("LINKED", None),
        ("UNRESOLVED", "item-001"),
        ("AMBIGUOUS", "item-001"),
    ):
        with pytest.raises(ValidationError):
            TranscriptReviewLinkResponse(
                relation="CITES",
                resolution=resolution,
                target_item_id=target,
                label="Link",
            )


def _course_catalog(boundary: tuple[str, ...]) -> PublicCourseCatalog:
    return PublicCourseCatalog.model_validate(
        {
            "schema_version": "1",
            "reviewed_on": date(2026, 9, 27),
            "source": {
                "repository": "owner/repository",
                "revision": "a" * 40,
                "url": "https://example.test/source",
            },
            "publication_boundary": boundary,
            "institutions": [
                {
                    "id": "institution",
                    "name": "Institution",
                    "courses": [
                        {
                            "id": "institution.course",
                            "code": "COURSE-1",
                            "materials_status": "published",
                        }
                    ],
                }
            ],
            "unresolved_collections": [],
        }
    )


def _project_catalog(topics: tuple[str, ...]) -> PublicProjectCatalog:
    return PublicProjectCatalog.model_validate(
        {
            "schema_version": "1",
            "projects": [
                {
                    "id": "project-1",
                    "slug": "project-1",
                    "name": "Project",
                    "tagline": "Tagline",
                    "summary": "Summary",
                    "status": "maintained",
                    "review": {
                        "record_version": "1.0.0",
                        "reviewed_on": date(2026, 9, 27),
                        "review_url": "https://example.test/review",
                    },
                    "source_revisions": [
                        {
                            "repository": "owner/repository",
                            "revision": "a" * 40,
                            "url": "https://example.test/source",
                        }
                    ],
                    "evidence": [
                        {
                            "label": "Evidence",
                            "url": "https://example.test/evidence",
                        }
                    ],
                    "topics": topics,
                    "purposes": ["Purpose"],
                }
            ],
        }
    )


def _transcript_item(flags: tuple[str, ...]) -> TranscriptReviewItemResponse:
    return TranscriptReviewItemResponse(
        item_id="item-001",
        category="CITATION",
        risk="REVIEW_REQUIRED",
        physical_page=1,
        source_text="source",
        explanation="explanation",
        flags=flags,
    )


def test__new_tuple_members_and_counts_have_exact_bounds() -> None:
    course_boundary = tuple(f"{index:02d}" + "x" * 498 for index in range(20))
    assert len(_course_catalog(course_boundary).publication_boundary) == 20
    for boundary in (
        course_boundary + ("extra",),
        ("x" * 501,),
        ("duplicate", "duplicate"),
    ):
        with pytest.raises(ValidationError):
            _course_catalog(boundary)

    topics = tuple(f"{index:02d}" + "x" * 158 for index in range(20))
    assert len(_project_catalog(topics).projects[0].topics) == 20
    for invalid_topics in (
        topics + ("extra",),
        ("x" * 161,),
        ("duplicate", "duplicate"),
    ):
        with pytest.raises(ValidationError):
            _project_catalog(invalid_topics)

    flags = tuple(f"flag-{index}" for index in range(100))
    assert len(_transcript_item(flags).flags) == 100
    for invalid_flags in (flags + ("extra",), ("x" * 201,)):
        with pytest.raises(ValidationError):
            _transcript_item(invalid_flags)

    summary = TranscriptReviewDocumentSummaryResponse(
        document_id="document-001",
        display_name="Document",
        source_id="source:001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=1,
        physical_page_count=1,
        total_items=MAX_COUNT,
        pending_items=MAX_COUNT,
        categories=(),
    )
    assert summary.total_items == MAX_COUNT
    with pytest.raises(ValidationError):
        summary.model_copy(update={"total_items": MAX_COUNT + 1}).__class__(
            **{
                **summary.model_dump(),
                "total_items": MAX_COUNT + 1,
            }
        )
