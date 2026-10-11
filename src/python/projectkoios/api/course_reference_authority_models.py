from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ContentId = Annotated[
    str,
    Field(
        min_length=73,
        max_length=512,
        pattern=r"^[a-z][a-z0-9.-]*:sha256:[0-9a-f]{64}$",
    ),
]
Citekey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}$",
    ),
]
BoundedText = Annotated[str, Field(min_length=1, max_length=4096)]
UtcTimestamp = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("idempotency_key", check_fields=False)
    @classmethod
    def bounded_idempotency_key(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("idempotency key exceeds its byte limit")
        return value


class IdentityDisposition(StrEnum):
    ACCEPT_EXISTING = "ACCEPT_EXISTING"
    ACCEPT_NEW = "ACCEPT_NEW"
    MERGE = "MERGE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class AssetDisposition(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class CourseReferenceFailureCode(StrEnum):
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    REVISION_STALE = "REVISION_STALE"
    TARGET_STALE = "TARGET_STALE"
    CONCURRENT_DECISION = "CONCURRENT_DECISION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INVALID_DISPOSITION = "INVALID_DISPOSITION"
    OWNER_MALFORMED = "OWNER_MALFORMED"
    OWNER_UNAVAILABLE = "OWNER_UNAVAILABLE"


class CourseReferenceFailureResponse(StrictModel):
    code: CourseReferenceFailureCode
    detail: str = Field(min_length=1, max_length=500)


class CourseReferenceScopeResponse(StrictModel):
    scope_id: ContentId
    course_id: str = Field(min_length=1, max_length=4096)
    course_title: str = Field(min_length=1, max_length=500)
    manifest_id: ContentId
    manifest_sha256: Sha256
    inventory_id: ContentId
    total: int = Field(ge=1, le=10_000)
    ordered_selection_ids: tuple[ContentId, ...] = Field(
        min_length=1,
        max_length=10_000,
    )

    @model_validator(mode="after")
    def exact_total(self) -> CourseReferenceScopeResponse:
        if self.total != len(self.ordered_selection_ids):
            raise ValueError("scope total differs from selection IDs")
        return self


class CourseReferenceSelectionResponse(StrictModel):
    scope_id: ContentId
    selection_id: ContentId
    locator_binding_id: ContentId
    course_id: str = Field(min_length=1, max_length=4096)
    manifest_id: ContentId
    inventory_id: ContentId
    ordinal: int = Field(ge=1, le=10_000)
    origin: Literal["preserved-manuscript", "directed-reference-scope"]
    role: Literal["manuscript-bibliography"]
    display_citekey: Citekey
    display_citekey_status: Literal["observed", "proposed-noncanonical"]
    reference_locator: ContentId
    previous_selection_id: ContentId | None
    next_selection_id: ContentId | None


class ReferenceCandidateResponse(StrictModel):
    candidate_id: ContentId
    proposed_citekey: Citekey
    entry_type: str = Field(min_length=1, max_length=4096)
    title: str | None = Field(default=None, min_length=1, max_length=4096)
    authors: tuple[str, ...] = Field(max_length=256)
    year: str | None = Field(default=None, min_length=1, max_length=4096)
    doi: str | None = Field(default=None, min_length=1, max_length=4096)
    isbn: str | None = Field(default=None, min_length=1, max_length=4096)
    url: str | None = Field(default=None, min_length=1, max_length=4096)
    eprint: str | None = Field(default=None, min_length=1, max_length=4096)
    identity_status: str = Field(min_length=1, max_length=4096)
    citekey_status: str = Field(min_length=1, max_length=4096)
    source_observation_ids: tuple[ContentId, ...] = Field(max_length=256)

    @field_validator(
        "entry_type",
        "title",
        "year",
        "doi",
        "isbn",
        "url",
        "eprint",
        "identity_status",
        "citekey_status",
    )
    @classmethod
    def no_control_text(cls, value: str | None) -> str | None:
        if value is not None and _CONTROL_CHARACTER.search(value) is not None:
            raise ValueError(
                "candidate display text contains a control character"
            )
        return value

    @field_validator("authors")
    @classmethod
    def bounded_authors(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            not value
            or len(value.encode("utf-8")) > 4096
            or _CONTROL_CHARACTER.search(value) is not None
            for value in values
        ):
            raise ValueError("candidate authors contain unsafe display text")
        return values


class ObservedCandidateEntryResponse(StrictModel):
    observation_id: ContentId
    source_id: str = Field(min_length=1, max_length=4096)
    asserted_source_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
    )
    bibliography_sha256: Sha256
    bibliography_byte_size: int = Field(gt=0)
    entry_index: int = Field(ge=0)
    observed_citekey: Citekey
    entry_sha256: Sha256
    entry_byte_size: int = Field(gt=0)


class RenderedCandidateEntryResponse(StrictModel):
    entry_id: ContentId
    citekey: Citekey
    entry_type: str = Field(min_length=1, max_length=4096)
    normalized_fields: tuple[tuple[str, str], ...] = Field(max_length=256)
    source_observation_ids: tuple[ContentId, ...] = Field(max_length=256)
    rendered_sha256: Sha256
    rendered_byte_size: int = Field(gt=0)


class ReferenceRecordMatchResponse(StrictModel):
    record_id: ContentId
    citekey: Citekey
    bibtex_sha256: Sha256
    bibtex_byte_size: int = Field(gt=0)
    authority_status: Literal["non-authoritative-discrepancy-observation"]
    kind: Literal[
        "exact-observed-key-and-bytes",
        "exact-rendered-key-and-bytes",
        "same-key-different-bytes",
        "same-observed-bytes-different-key",
        "same-rendered-bytes-different-key",
    ]


class IngestionArtifactLinkResponse(StrictModel):
    link_id: ContentId
    asset_observation_id: ContentId
    source_id: str = Field(min_length=1, max_length=1024)
    document_id: ContentId
    artifact_verification_result_id: ContentId


class ReferenceAssetResponse(StrictModel):
    candidate_id: ContentId
    asset_observation_id: ContentId
    sha256: Sha256
    byte_size: int = Field(ge=0, le=4_000_000_000)
    rights_status: str = Field(min_length=1, max_length=4096)
    asset_status: str = Field(min_length=1, max_length=4096)
    runtime_availability: Literal["available", "unavailable", "unknown"]
    runtime_evidence_id: ContentId | None
    document_binding_ids: tuple[ContentId, ...] = Field(max_length=10_000)
    ingestion_evidence_ids: tuple[ContentId, ...] = Field(max_length=10_000)
    ingestion_artifact_links: tuple[IngestionArtifactLinkResponse, ...] = Field(
        max_length=10_000
    )


class CurrentDecisionHeadResponse(StrictModel):
    decision_id: ContentId
    subject_id: ContentId
    context_id: str = Field(min_length=1, max_length=4096)
    dimension: Literal["reference-identity", "canonical-asset"]
    decision: str = Field(min_length=1, max_length=64)
    actor_id: str = Field(min_length=1, max_length=4096)
    authority_scope: Literal[
        "reference-identity-curator",
        "canonical-asset-curator",
    ]
    actor_verification_record_id: ContentId
    decided_at: UtcTimestamp


class ActiveReferenceAuthorityResponse(StrictModel):
    candidate_id: ContentId
    state_projection_id: ContentId
    bibliographic_work_id: ContentId
    active_citekey: Citekey
    alias_citekeys: tuple[Citekey, ...] = Field(max_length=256)
    identity_decision_id: ContentId
    source_asset_id: ContentId | None
    canonical_asset_decision_id: ContentId | None
    authority_binding_id: ContentId | None


class CourseReferenceQueueItemResponse(StrictModel):
    selection: CourseReferenceSelectionResponse
    resolution: Literal[
        "ready",
        "rendered-locator-unavailable",
        "display-guard-mismatch",
        "candidate-unavailable",
        "candidate-ambiguous",
        "candidate-display-guard-mismatch",
        "owner-evidence-malformed",
    ]
    candidate: ReferenceCandidateResponse | None
    observations: tuple[ObservedCandidateEntryResponse, ...] = Field(
        max_length=256
    )
    rendered_entry: RenderedCandidateEntryResponse | None
    record_matches: tuple[ReferenceRecordMatchResponse, ...] = Field(
        max_length=10_000
    )
    assets: tuple[ReferenceAssetResponse, ...] = Field(max_length=10_000)
    current_identity_decisions: tuple[CurrentDecisionHeadResponse, ...] = Field(
        max_length=32
    )
    current_asset_decision: CurrentDecisionHeadResponse | None
    active_authority: ActiveReferenceAuthorityResponse | None
    allowed_identity_actions: tuple[IdentityDisposition, ...] = Field(
        max_length=5
    )
    allowed_asset_actions: tuple[AssetDisposition, ...] = Field(max_length=3)
    asset_plan_id: ContentId | None
    item_revision_id: ContentId


class CourseReferenceQueueResponse(StrictModel):
    contract_id: Literal[
        "projectkoios.references.course-reference-authority@0.1.0"
    ] = "projectkoios.references.course-reference-authority@0.1.0"
    control_class: Literal["CONTROL"] = "CONTROL"
    queue_id: ContentId
    request_id: ContentId
    scope: CourseReferenceScopeResponse
    items: tuple[CourseReferenceQueueItemResponse, ...] = Field(
        min_length=1,
        max_length=10_000,
    )
    active_authorities: tuple[ActiveReferenceAuthorityResponse, ...] = Field(
        max_length=10_000
    )
    source_export_result_id: ContentId
    render_result_id: ContentId
    review_projection_id: ContentId
    state_projection_ids: tuple[ContentId, ...] = Field(max_length=10_000)

    @model_validator(mode="after")
    def exact_scope(self) -> CourseReferenceQueueResponse:
        if tuple(item.selection.selection_id for item in self.items) != (
            self.scope.ordered_selection_ids
        ):
            raise ValueError("queue differs from the Courses scope order")
        return self


class ReviewActorRequest(RequestModel):
    actor_id: str = Field(min_length=1, max_length=4096)
    verification_record_id: ContentId
    verification_method: str = Field(min_length=1, max_length=4096)


class IdentityDecisionRequest(RequestModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_queue_id: ContentId
    expected_item_revision_id: ContentId
    expected_current_decision_id: ContentId | None = None
    disposition: IdentityDisposition
    target_state_projection_id: ContentId | None = None
    canonical_citekey: Citekey | None = None
    alias_citekeys: tuple[Citekey, ...] = Field(max_length=256)
    selected_record_match_ids: tuple[ContentId, ...] = Field(max_length=10_000)
    rationale: BoundedText
    decided_at: UtcTimestamp
    actor: ReviewActorRequest


class AssetCompetitorDecisionRequest(RequestModel):
    asset_observation_id: ContentId
    disposition: AssetDisposition
    rationale: BoundedText


class AssetDecisionRequest(RequestModel):
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expected_queue_id: ContentId
    expected_item_revision_id: ContentId
    expected_identity_state_projection_id: ContentId
    expected_asset_plan_id: ContentId
    expected_current_decision_id: ContentId | None = None
    disposition: AssetDisposition
    competitors: tuple[AssetCompetitorDecisionRequest, ...] = Field(
        max_length=10_000
    )
    rationale: BoundedText
    decided_at: UtcTimestamp
    actor: ReviewActorRequest


class CourseReferenceDecisionReceiptResponse(StrictModel):
    receipt_id: ContentId
    result_id: ContentId
    request_id: ContentId
    preview_id: ContentId
    decision_id: ContentId
    dimension: Literal["reference-identity", "canonical-asset"]
    disposition: str = Field(min_length=1, max_length=64)
    state_projection_id: ContentId | None
    current_decision_id: ContentId
    refreshed_queue_id: ContentId
    refreshed_item_revision_id: ContentId
    refreshed_item: CourseReferenceQueueItemResponse
