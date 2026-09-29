from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal

from projectkoios.api.boundary_models import (
    MAX_COUNT,
    MAX_REGION_COORDINATE,
    OpaqueId,
)
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
BoundedText = Annotated[str, Field(max_length=100_000)]
BoundedLabel = Annotated[str, Field(min_length=1, max_length=500)]
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_MAX_PHYSICAL_PAGES = 1_000_000
MAX_EQUATION_REVIEW_CANDIDATES = 256
MAX_EQUATION_REVIEW_REVISIONS = 9_999


class EquationReviewDisposition(StrEnum):
    ACCEPT_TRANSCRIPTION = "ACCEPT_TRANSCRIPTION"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class EquationDisplayMode(StrEnum):
    INLINE = "INLINE"
    DISPLAY = "DISPLAY"


class EquationReviewStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    LEGACY_ACCEPTANCE = "LEGACY_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class EquationReviewFailureCode(StrEnum):
    PROPOSAL_STALE = "EQUATION_REVIEW_PROPOSAL_STALE"
    EVIDENCE_STALE = "EQUATION_REVIEW_EVIDENCE_STALE"
    REVISION_STALE = "EQUATION_REVIEW_REVISION_STALE"
    REVIEWER_LATEX_NONCANONICAL = "EQUATION_REVIEW_REVIEWER_LATEX_NONCANONICAL"
    RENDER_STALE = "EQUATION_REVIEW_RENDER_STALE"
    EDIT_AFTER_RENDER = "EQUATION_REVIEW_EDIT_AFTER_RENDER"
    CONCURRENT_DECISION = "EQUATION_REVIEW_CONCURRENT_DECISION"
    PARTIAL_OUTPUT = "EQUATION_REVIEW_PARTIAL_OUTPUT"
    OWNER_UNAVAILABLE = "EQUATION_REVIEW_OWNER_UNAVAILABLE"


class EquationSourceIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: OpaqueId
    source_name: str = Field(min_length=1, max_length=500)
    source_sha256: Sha256
    physical_page: int = Field(ge=1, le=_MAX_PHYSICAL_PAGES)

    @model_validator(mode="after")
    def has_path_free_source_name(self) -> EquationSourceIdentityResponse:
        if (
            "/" in self.source_name
            or "\\" in self.source_name
            or _CONTROL_CHARACTER.search(self.source_name) is not None
        ):
            raise ValueError("equation source names cannot contain path syntax")
        return self


class EquationRegionEvidenceResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )

    coordinate_space: Literal["PDF_POINTS"]
    x: float = Field(ge=0, le=MAX_REGION_COORDINATE)
    y: float = Field(ge=0, le=MAX_REGION_COORDINATE)
    width: float = Field(gt=0, le=MAX_REGION_COORDINATE)
    height: float = Field(gt=0, le=MAX_REGION_COORDINATE)
    image_sha256: Sha256

    @model_validator(mode="after")
    def remains_in_bounded_coordinate_space(
        self,
    ) -> EquationRegionEvidenceResponse:
        if (
            self.x + self.width > MAX_REGION_COORDINATE
            or self.y + self.height > MAX_REGION_COORDINATE
        ):
            raise ValueError("equation region exceeds the coordinate bound")
        return self


class DeterministicEquationEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    detector: BoundedLabel
    detector_version: BoundedLabel
    evidence_sha256: Sha256
    extracted_text: BoundedText | None


class EquationModelProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_name: BoundedLabel
    model_sha256: Sha256
    prompt_version: BoundedLabel
    request_id: OpaqueId
    result_id: OpaqueId

    @model_validator(mode="after")
    def has_path_free_labels(self) -> EquationModelProvenanceResponse:
        _path_free_provenance_label(self.model_name)
        _path_free_provenance_label(self.prompt_version)
        return self


class PendingEquationAssistanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["PENDING", "FAILED"]
    method: BoundedLabel | None
    proposal_sha256: None
    proposed_latex: None


class ProposedEquationAssistanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["PROPOSED"]
    method: BoundedLabel
    proposal_sha256: Sha256
    proposed_latex: str = Field(min_length=1, max_length=100_000)
    attempt_id: OpaqueId | None = None
    model_provenance: EquationModelProvenanceResponse | None = None

    @model_validator(mode="after")
    def has_non_path_method(self) -> ProposedEquationAssistanceResponse:
        _path_free_provenance_label(self.method, allow_separator=True)
        return self


AssistedEquationProposalResponse = Annotated[
    PendingEquationAssistanceResponse | ProposedEquationAssistanceResponse,
    Field(discriminator="status"),
]


class EquationRenderConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    renderer_id: BoundedLabel
    renderer_version: BoundedLabel
    rendered_reviewer_latex_sha256: Sha256
    rendered_obsidian_markdown_sha256: Sha256

    @model_validator(mode="after")
    def has_path_free_renderer(self) -> EquationRenderConfirmation:
        _path_free_provenance_label(self.renderer_id)
        _path_free_provenance_label(self.renderer_version)
        return self


class EquationReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: EquationReviewStatus
    schema_version: Literal[2, 3]
    disposition: EquationReviewDisposition
    assistance_proposal_sha256: Sha256 | None
    reviewer_latex: str | None = Field(max_length=100_000)
    reviewer_latex_sha256: Sha256 | None
    obsidian_markdown: str | None = Field(max_length=100_005)
    obsidian_markdown_sha256: Sha256 | None
    display_mode: EquationDisplayMode | None
    render_confirmation: EquationRenderConfirmation | None
    note: str = Field(max_length=10_000)
    revision: int = Field(ge=1, le=MAX_EQUATION_REVIEW_REVISIONS)
    revision_id: OpaqueId
    recorded_at_utc: AwareDatetime

    @model_validator(mode="after")
    def is_exact_owner_revision(self) -> EquationReviewDecision:
        offset = self.recorded_at_utc.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError("equation decision timestamps must be UTC")
        accepted_values = (
            self.reviewer_latex,
            self.reviewer_latex_sha256,
            self.obsidian_markdown,
            self.obsidian_markdown_sha256,
            self.display_mode,
            self.render_confirmation,
        )
        if self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION:
            if self.assistance_proposal_sha256 is None:
                raise ValueError(
                    "accepted transcriptions require an assistance "
                    "proposal hash"
                )
            if self.schema_version == 2:
                if self.status is not EquationReviewStatus.LEGACY_ACCEPTANCE:
                    raise ValueError("legacy acceptance status is inconsistent")
                if any(value is not None for value in accepted_values):
                    raise ValueError(
                        "legacy acceptance cannot claim canonical "
                        "representations"
                    )
                return self
            if self.status is not EquationReviewStatus.ACCEPTED:
                raise ValueError("accepted review status is inconsistent")
            if any(value is None for value in accepted_values):
                raise ValueError(
                    "accepted schema-3 revision is missing representations"
                )
            assert self.reviewer_latex is not None
            assert self.reviewer_latex_sha256 is not None
            assert self.obsidian_markdown is not None
            assert self.obsidian_markdown_sha256 is not None
            assert self.display_mode is not None
            assert self.render_confirmation is not None
            if not self.reviewer_latex:
                raise ValueError("reviewer LaTeX cannot be empty")
            if _text_sha256(self.reviewer_latex) != self.reviewer_latex_sha256:
                raise ValueError("reviewer LaTeX hash is inconsistent")
            canonical_markdown = _canonical_obsidian_markdown(
                self.reviewer_latex,
                self.display_mode,
            )
            if self.obsidian_markdown != canonical_markdown:
                raise ValueError("Obsidian Markdown is not canonical")
            if (
                _text_sha256(self.obsidian_markdown)
                != self.obsidian_markdown_sha256
            ):
                raise ValueError("Obsidian Markdown hash is inconsistent")
            if (
                self.render_confirmation.rendered_reviewer_latex_sha256
                != self.reviewer_latex_sha256
                or self.render_confirmation.rendered_obsidian_markdown_sha256
                != self.obsidian_markdown_sha256
            ):
                raise ValueError("render confirmation is stale")
            return self
        if any(value is not None for value in accepted_values):
            raise ValueError(
                "non-acceptance cannot claim accepted representations"
            )
        expected_status = (
            EquationReviewStatus.REJECTED
            if self.disposition is EquationReviewDisposition.REJECT_CANDIDATE
            else EquationReviewStatus.REVISION_REQUIRED
        )
        if self.status is not expected_status:
            raise ValueError("non-acceptance review status is inconsistent")
        return self


class EquationReviewDecisionResponse(EquationReviewDecision):
    candidate_id: OpaqueId


class EquationReviewFailureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: EquationReviewFailureCode
    detail: str = Field(min_length=1, max_length=500)


class EquationReviewCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: OpaqueId
    source: EquationSourceIdentityResponse
    region: EquationRegionEvidenceResponse
    deterministic_evidence: DeterministicEquationEvidenceResponse
    display_mode: EquationDisplayMode
    assistance: AssistedEquationProposalResponse | None
    status: EquationReviewStatus
    current_revision: int = Field(ge=0, le=MAX_EQUATION_REVIEW_REVISIONS)
    expected_previous_revision: int = Field(
        ge=0,
        le=MAX_EQUATION_REVIEW_REVISIONS,
    )
    decision: EquationReviewDecision | None

    @model_validator(mode="after")
    def has_consistent_review_state(self) -> EquationReviewCandidateResponse:
        if self.decision is None:
            if (
                self.status is not EquationReviewStatus.UNREVIEWED
                or self.current_revision != 0
                or self.expected_previous_revision != 0
            ):
                raise ValueError("unreviewed candidate state is inconsistent")
            return self
        if (
            self.status is not self.decision.status
            or self.current_revision != self.decision.revision
            or self.expected_previous_revision != self.decision.revision
        ):
            raise ValueError("reviewed candidate state is inconsistent")
        return self


class EquationReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: OpaqueId
    total: int = Field(ge=0, le=MAX_COUNT)
    decided: int = Field(ge=0, le=MAX_COUNT)
    items: tuple[EquationReviewCandidateResponse, ...] = Field(
        max_length=MAX_EQUATION_REVIEW_CANDIDATES
    )

    @model_validator(mode="after")
    def has_consistent_queue(self) -> EquationReviewQueueResponse:
        if self.total != len(self.items):
            raise ValueError("equation candidate total must match the queue")
        if self.decided != sum(
            candidate.decision is not None for candidate in self.items
        ):
            raise ValueError("equation decided count must match the queue")
        candidate_ids = [str(item.candidate_id) for item in self.items]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("equation candidate ids must be unique")
        if any(
            candidate.source.document_id != self.document_id
            for candidate in self.items
        ):
            raise ValueError("equation source document must match the queue")
        return self


class EquationReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: EquationReviewDisposition
    assistance_proposal_sha256: Sha256 | None
    reviewer_latex: str | None = Field(max_length=100_000)
    display_mode: EquationDisplayMode | None
    render_confirmation: EquationRenderConfirmation | None
    note: str = Field(max_length=10_000)
    expected_previous_revision: int = Field(
        ge=0,
        lt=MAX_EQUATION_REVIEW_REVISIONS,
    )

    @model_validator(mode="after")
    def has_disposition_specific_representations(
        self,
    ) -> EquationReviewDecisionRequest:
        values = (
            self.reviewer_latex,
            self.display_mode,
            self.render_confirmation,
        )
        if self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION:
            if self.assistance_proposal_sha256 is None:
                raise ValueError(
                    "accepted transcriptions require an assistance "
                    "proposal hash"
                )
            if (
                any(value is None for value in values)
                or not self.reviewer_latex
            ):
                raise ValueError(
                    "accepted transcriptions require rendered reviewer LaTeX"
                )
        elif any(value is not None for value in values):
            raise ValueError(
                "non-acceptance cannot carry accepted representations"
            )
        return self


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="strict")).hexdigest()


def _canonical_obsidian_markdown(
    reviewer_latex: str,
    display_mode: EquationDisplayMode,
) -> str:
    body = _canonical_reviewer_latex_body(reviewer_latex)
    if display_mode is EquationDisplayMode.INLINE:
        return f"${body}$"
    return f"$$\n{body}\n$$"


def _canonical_reviewer_latex_body(value: str) -> str:
    if (
        value != value.strip()
        or "\r" in value
        or unicodedata.normalize("NFC", value) != value
        or (
            len(value) >= 2
            and value.startswith("$")
            and value.endswith("$")
            and _is_unescaped(value, len(value) - 1)
        )
    ):
        raise ValueError("reviewer LaTeX is not a canonical math body")
    return value


def _is_unescaped(value: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 0


def _path_free_provenance_label(
    value: str,
    *,
    allow_separator: bool = False,
) -> None:
    if (
        _CONTROL_CHARACTER.search(value) is not None
        or value.startswith(("/", "\\"))
        or "://" in value
        or re.match(r"^[A-Za-z]:[/\\]", value) is not None
        or "\\" in value
        or "../" in value
        or "/.." in value
        or (not allow_separator and "/" in value)
    ):
        raise ValueError("provenance labels cannot contain path syntax")
