from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CitationDecisionDisposition(StrEnum):
    ACCEPT_CITATION = "ACCEPT_CITATION"
    REJECT_CANDIDATES = "REJECT_CANDIDATES"
    PARTIAL_SUPPORT = "PARTIAL_SUPPORT"
    CORPUS_GAP = "CORPUS_GAP"
    NO_CITATION_REQUIRED = "NO_CITATION_REQUIRED"


class ManuscriptEquationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latex: str
    display: bool


class CitationCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    citation_key: str | None
    bibtex_entry_present: bool
    score: float
    file: str
    physical_page: int = Field(ge=1)
    printed_page: str
    passage_id: str
    passage: str


class CitationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: CitationDecisionDisposition
    selected_citation_keys: list[str] = Field(
        default_factory=list, max_length=20
    )
    note: str = Field(default="", max_length=4_000)


class CitationDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    disposition: CitationDecisionDisposition
    selected_citation_keys: list[str]
    note: str
    revision: int = Field(ge=1)
    updated_at_utc: str


class CitationReviewSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    lines: str
    claim: str
    recommendation_relationship: str
    recommended_keys: list[str]
    evaluation_status: str
    decision: CitationDecisionResponse | None


class CitationReviewDetailResponse(CitationReviewSummaryResponse):
    query: str
    manuscript_excerpt_latex: str
    manuscript_equations: list[ManuscriptEquationResponse]
    expected_keys: list[str]
    expected_keys_available: list[str]
    expected_outcome: str
    recommendation: str
    candidates: list[CitationCandidateResponse]


class CitationReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: str
    manuscript_sha256: str
    total: int = Field(ge=0)
    decided: int = Field(ge=0)
    items: list[CitationReviewSummaryResponse]
