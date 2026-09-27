from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"


class TranscriptReviewStatus(StrEnum):
    AUTOMATED_UNREVIEWED = "AUTOMATED_UNREVIEWED"


class TranscriptReviewCategory(StrEnum):
    TRANSCRIPT_DIFF = "TRANSCRIPT_DIFF"
    DEHYPHENATION = "DEHYPHENATION"
    PAGE_NUMBER = "PAGE_NUMBER"
    FRONT_MATTER = "FRONT_MATTER"
    PRIVATE_USE_GLYPH = "PRIVATE_USE_GLYPH"
    EQUATION = "EQUATION"
    FIGURE = "FIGURE"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    CITATION = "CITATION"


class TranscriptReviewRisk(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INFORMATIONAL = "INFORMATIONAL"


class TranscriptReviewLinkRelation(StrEnum):
    CITES = "CITES"
    CITED_BY = "CITED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    HAS_DERIVATIVE = "HAS_DERIVATIVE"


class TranscriptReviewLinkResolution(StrEnum):
    LINKED = "LINKED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class TranscriptReviewRegionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)

    @model_validator(mode="after")
    def has_positive_area(self) -> TranscriptReviewRegionResponse:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("transcript review region must have positive area")
        return self


class TranscriptReviewLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: TranscriptReviewLinkRelation
    resolution: TranscriptReviewLinkResolution
    target_item_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )
    label: str = Field(min_length=1, max_length=500)


class TranscriptReviewItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    category: TranscriptReviewCategory
    risk: TranscriptReviewRisk
    physical_page: int = Field(ge=1)
    printed_page: str | None = Field(default=None, max_length=100)
    region: TranscriptReviewRegionResponse | None = None
    source_text: str = Field(max_length=100_000)
    predecessor_text: str | None = Field(default=None, max_length=100_000)
    projected_text: str | None = Field(default=None, max_length=100_000)
    explanation: str = Field(min_length=1, max_length=10_000)
    flags: tuple[str, ...] = Field(default=(), max_length=100)
    preview_asset_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )
    links: tuple[TranscriptReviewLinkResponse, ...] = Field(
        default=(),
        max_length=500,
    )


class TranscriptReviewDocumentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=500)
    status: TranscriptReviewStatus
    artifact_generation: int = Field(ge=1)
    physical_page_count: int = Field(ge=1)
    total_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)
    categories: tuple[TranscriptReviewCategory, ...] = Field(max_length=9)

    @model_validator(mode="after")
    def has_consistent_summary_counts(
        self,
    ) -> TranscriptReviewDocumentSummaryResponse:
        if self.pending_items > self.total_items:
            raise ValueError("pending transcript items cannot exceed the total")
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("transcript review categories must be unique")
        return self


class TranscriptReviewDocumentResponse(TranscriptReviewDocumentSummaryResponse):
    manifest_id: str = Field(min_length=1, max_length=500)
    clean_artifact_id: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: tuple[str, ...] = Field(max_length=100)
    items: tuple[TranscriptReviewItemResponse, ...] = Field(max_length=100_000)

    @model_validator(mode="after")
    def has_consistent_detail_counts(self) -> TranscriptReviewDocumentResponse:
        if self.total_items != len(self.items):
            raise ValueError("transcript item total must match the detail")
        item_categories = tuple(
            sorted(
                {item.category for item in self.items},
                key=lambda item: item.value,
            )
        )
        if self.categories != item_categories:
            raise ValueError("transcript categories must match the detail")
        return self


class TranscriptReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    title: str = Field(min_length=1, max_length=500)
    status: TranscriptReviewStatus
    total_documents: int = Field(ge=0)
    total_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)
    documents: tuple[TranscriptReviewDocumentSummaryResponse, ...] = Field(
        max_length=10_000,
    )

    @model_validator(mode="after")
    def has_consistent_queue_counts(self) -> TranscriptReviewQueueResponse:
        if self.total_documents != len(self.documents):
            raise ValueError("transcript document total must match the queue")
        if self.total_items != sum(
            document.total_items for document in self.documents
        ):
            raise ValueError("transcript item total must match the queue")
        if self.pending_items != sum(
            document.pending_items for document in self.documents
        ):
            raise ValueError("pending transcript total must match the queue")
        return self
