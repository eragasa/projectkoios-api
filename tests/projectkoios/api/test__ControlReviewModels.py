from __future__ import annotations

import hashlib

import pytest
from projectkoios.api.boundary_models import (
    MAX_COUNT,
    MAX_OPAQUE_ID_LENGTH,
    MAX_REGION_COORDINATE,
    OpaqueId,
    SafeRelativePosixPath,
)
from projectkoios.api.equation_review.models import (
    ProposedEquationAssistanceResponse,
)
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewItemResponse,
    TranscriptReviewLinkResponse,
    TranscriptReviewQueueResponse,
    TranscriptReviewRegionResponse,
)
from pydantic import TypeAdapter, ValidationError

_REAL_ASSISTANCE_METHOD = (
    "ollama-multimodal-region-processor/1;model=qwen3.5:9b;"
    "model_sha256="
    "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7;"
    "prompt=region-transcription-v1;request=ollama-multimodal-request:sha256:"
    "7ceb7620a8851360d1f585dd5724c20499e4db846d1a1a852a0750d0a4f45bb8;"
    "result=ollama-multimodal-result:sha256:"
    "d7f299517f7c4e67b7137c280143ec0d4d23b7a2db1df5262dad05293141492f"
)
_PROPOSAL = r"E = mc^2"
_PROPOSAL_SHA256 = hashlib.sha256(_PROPOSAL.encode()).hexdigest()


def _summary() -> TranscriptReviewDocumentSummaryResponse:
    return TranscriptReviewDocumentSummaryResponse(
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


def test__transcript_queue__requires_consistent_counts() -> None:
    with pytest.raises(ValidationError):
        TranscriptReviewQueueResponse(
            review_id="synthetic-review",
            title="Synthetic review",
            status="AUTOMATED_UNREVIEWED",
            total_documents=1,
            total_items=1,
            pending_items=1,
            documents=(_summary(),),
        )


def test__transcript_region__requires_positive_geometry() -> None:
    with pytest.raises(ValidationError):
        TranscriptReviewRegionResponse(x0=10, y0=20, x1=10, y1=30)


def test__opaque_ids__enforce_exact_length_and_reject_path_syntax() -> None:
    assert len(OpaqueId("a" * MAX_OPAQUE_ID_LENGTH)) == 256

    for value in (
        "a" * (MAX_OPAQUE_ID_LENGTH + 1),
        "/absolute",
        "../traversal",
        "segment/child",
        r"segment\child",
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


def test__safe_relative_paths_are_normalized_posix_display_paths() -> None:
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
        r"a\b",
        "a\x00b",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


def test__assistance_method__accepts_bounded_opaque_real_provenance() -> None:
    assistance = ProposedEquationAssistanceResponse(
        status="AUTOMATED_UNREVIEWED",
        attempt_id="equation-assisted-attempt:fixture",
        method=_REAL_ASSISTANCE_METHOD,
        proposal_sha256=_PROPOSAL_SHA256,
        proposed_latex=_PROPOSAL,
    )

    assert assistance.method == _REAL_ASSISTANCE_METHOD


@pytest.mark.parametrize(
    "method",
    (
        "x" * 501,
        "unsafe\nmethod",
        "unsafe\u202emethod",
        "unsafe\ud800method",
    ),
)
def test__assistance_method__rejects_oversized_or_control_text(
    method: str,
) -> None:
    with pytest.raises(ValidationError):
        ProposedEquationAssistanceResponse(
            status="AUTOMATED_UNREVIEWED",
            attempt_id="equation-assisted-attempt:fixture",
            method=method,
            proposal_sha256=_PROPOSAL_SHA256,
            proposed_latex=_PROPOSAL,
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
    ["/absolute", "../traversal", r"path\value", "x" * 257],
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
                relation=resolution and "CITES",
                resolution=resolution,
                target_item_id=target,
                label="Link",
            )


def test__transcript_tuple_members_and_counts_have_exact_bounds() -> None:
    flags = tuple(f"flag-{index}" for index in range(100))
    assert len(_item_with_flags(flags).flags) == 100
    for invalid_flags in (flags + ("extra",), ("x" * 201,)):
        with pytest.raises(ValidationError):
            _item_with_flags(invalid_flags)

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
        TranscriptReviewDocumentSummaryResponse(
            **{
                **summary.model_dump(),
                "total_items": MAX_COUNT + 1,
            }
        )


def _item_with_flags(flags: tuple[str, ...]) -> TranscriptReviewItemResponse:
    return TranscriptReviewItemResponse(
        item_id="item-001",
        category="CITATION",
        risk="REVIEW_REQUIRED",
        physical_page=1,
        source_text="source",
        explanation="explanation",
        flags=flags,
    )
