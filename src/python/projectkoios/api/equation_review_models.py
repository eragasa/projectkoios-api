from __future__ import annotations

import re
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


class EquationReviewDisposition(StrEnum):
    ACCEPT_TRANSCRIPTION = "ACCEPT_TRANSCRIPTION"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    REVISION_REQUIRED = "REVISION_REQUIRED"


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


AssistedEquationProposalResponse = Annotated[
    PendingEquationAssistanceResponse | ProposedEquationAssistanceResponse,
    Field(discriminator="status"),
]


class EquationReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    disposition: EquationReviewDisposition
    assistance_proposal_sha256: Sha256 | None
    note: str = Field(max_length=10_000)
    revision: int = Field(ge=1, le=MAX_COUNT)
    updated_at_utc: AwareDatetime

    @model_validator(mode="after")
    def is_utc_and_binds_acceptance(self) -> EquationReviewDecisionResponse:
        offset = self.updated_at_utc.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError("equation decision timestamps must be UTC")
        if (
            self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
            and self.assistance_proposal_sha256 is None
        ):
            raise ValueError(
                "accepted transcriptions require an assistance proposal hash"
            )
        return self


class EquationReviewCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: OpaqueId
    source: EquationSourceIdentityResponse
    region: EquationRegionEvidenceResponse
    deterministic_evidence: DeterministicEquationEvidenceResponse
    assistance: AssistedEquationProposalResponse | None
    decision: EquationReviewDecisionResponse | None


class EquationReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: OpaqueId
    total: int = Field(ge=0, le=MAX_COUNT)
    decided: int = Field(ge=0, le=MAX_COUNT)
    items: tuple[EquationReviewCandidateResponse, ...] = Field(
        max_length=100_000
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
    note: str = Field(max_length=10_000)

    @model_validator(mode="after")
    def accepted_transcription_names_proposal(
        self,
    ) -> EquationReviewDecisionRequest:
        if (
            self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
            and self.assistance_proposal_sha256 is None
        ):
            raise ValueError(
                "accepted transcriptions require an assistance proposal hash"
            )
        return self
