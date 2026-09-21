from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LiteratureReviewPhase(StrEnum):
    PENDING = "PENDING"
    RETRIEVING = "RETRIEVING"
    ASSESSING = "ASSESSING"
    COMPLETE = "COMPLETE"


class LiteratureClaimStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    QUALIFIED = "QUALIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class ProvidedReferenceStatus(StrEnum):
    RECEIVED_NOT_INGESTED = "RECEIVED_NOT_INGESTED"
    INGESTED_AUTOMATED_UNREVIEWED = "INGESTED_AUTOMATED_UNREVIEWED"


class LiteratureEvidenceReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    citation_key: str | None
    physical_page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=4_000)


class LiteratureEquationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    latex: str
    interpretation: str


class LiteratureValidationFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_status: str
    finding: str
    conclusion: str
    evidence_labels: list[str]
    equations: list[LiteratureEquationResponse]


class LiteratureClaimProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    section: str
    claim: str
    evidence_count: int = Field(ge=0)
    status: LiteratureClaimStatus | None
    summary: str | None
    corrected_claim: str | None
    assumptions: list[str]
    evidence: list[LiteratureEvidenceReferenceResponse]
    source_requests: list[str]
    validation_frame: LiteratureValidationFrameResponse | None


class LiteratureStatusCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: int = Field(ge=0)
    qualified: int = Field(ge=0)
    contradicted: int = Field(ge=0)
    unresolved: int = Field(ge=0)


class ProvidedReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    claim_id: str
    citation_label: str
    doi_or_url: str | None
    note: str
    source_sha256: str
    byte_length: int = Field(ge=1)
    status: ProvidedReferenceStatus
    received_at_utc: str
    latest_generation: str | None
    duplicate: bool


class ProvidedReferenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProvidedReferenceResponse]


class LiteratureReviewProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    phase: LiteratureReviewPhase
    assessment_status: str
    claim_count: int = Field(ge=0)
    evidence_ready_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    completion_percent: float = Field(ge=0, le=100)
    status_counts: LiteratureStatusCountResponse
    human_disposition: str | None
    classifier_implementation_authorized: bool
    scientific_calculation_authorized: bool
    original_submission_markdown: str
    claims: list[LiteratureClaimProgressResponse]
