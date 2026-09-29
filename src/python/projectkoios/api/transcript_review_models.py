from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from projectkoios.api.boundary_models import (
    MAX_COUNT,
    MAX_REGION_COORDINATE,
    OpaqueId,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

_MAX_ARTIFACT_GENERATION = 1_000_000
_MAX_PHYSICAL_PAGES = 1_000_000
BoundedFlag = Annotated[str, Field(min_length=1, max_length=200)]
BoundedLimitation = Annotated[str, Field(min_length=1, max_length=2000)]


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
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    x0: float = Field(
        ge=0,
        le=MAX_REGION_COORDINATE,
        allow_inf_nan=False,
    )
    y0: float = Field(
        ge=0,
        le=MAX_REGION_COORDINATE,
        allow_inf_nan=False,
    )
    x1: float = Field(
        ge=0,
        le=MAX_REGION_COORDINATE,
        allow_inf_nan=False,
    )
    y1: float = Field(
        ge=0,
        le=MAX_REGION_COORDINATE,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def has_positive_area(self) -> TranscriptReviewRegionResponse:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("transcript review region must have positive area")
        return self


class TranscriptReviewLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: TranscriptReviewLinkRelation
    resolution: TranscriptReviewLinkResolution
    target_item_id: OpaqueId | None = None
    label: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def has_consistent_resolution(self) -> TranscriptReviewLinkResponse:
        has_target = self.target_item_id is not None
        if has_target is not (
            self.resolution is TranscriptReviewLinkResolution.LINKED
        ):
            raise ValueError("only linked transcript links have a target id")
        return self


class TranscriptReviewItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: OpaqueId
    category: TranscriptReviewCategory
    risk: TranscriptReviewRisk
    physical_page: int = Field(ge=1, le=_MAX_PHYSICAL_PAGES)
    printed_page: str | None = Field(default=None, min_length=1, max_length=100)
    region: TranscriptReviewRegionResponse | None = None
    source_text: str = Field(max_length=100_000)
    predecessor_text: str | None = Field(default=None, max_length=100_000)
    projected_text: str | None = Field(default=None, max_length=100_000)
    explanation: str = Field(min_length=1, max_length=10_000)
    flags: tuple[BoundedFlag, ...] = Field(default=(), max_length=100)
    preview_asset_id: OpaqueId | None = None
    links: tuple[TranscriptReviewLinkResponse, ...] = Field(
        default=(),
        max_length=500,
    )

    @model_validator(mode="after")
    def has_unique_flags_and_links(self) -> TranscriptReviewItemResponse:
        if len(self.flags) != len(set(self.flags)):
            raise ValueError("transcript item flags must be unique")
        link_identities = [
            (
                link.relation,
                link.resolution,
                str(link.target_item_id) if link.target_item_id else None,
                link.label,
            )
            for link in self.links
        ]
        if len(link_identities) != len(set(link_identities)):
            raise ValueError("transcript item links must be unique")
        return self


class TranscriptReviewDocumentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: OpaqueId
    display_name: str = Field(min_length=1, max_length=500)
    source_id: OpaqueId
    status: TranscriptReviewStatus
    artifact_generation: int = Field(ge=1, le=_MAX_ARTIFACT_GENERATION)
    physical_page_count: int = Field(ge=1, le=_MAX_PHYSICAL_PAGES)
    total_items: int = Field(ge=0, le=MAX_COUNT)
    pending_items: int = Field(ge=0, le=MAX_COUNT)
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
    manifest_id: OpaqueId
    clean_artifact_id: OpaqueId
    source_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    limitations: tuple[BoundedLimitation, ...] = Field(max_length=100)
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
        item_ids = [str(item.item_id) for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("transcript item ids must be unique")
        known_item_ids = set(item_ids)
        for item in self.items:
            if item.physical_page > self.physical_page_count:
                raise ValueError("transcript item page exceeds document pages")
            for link in item.links:
                if link.target_item_id is not None and (
                    str(link.target_item_id) not in known_item_ids
                    or link.target_item_id == item.item_id
                ):
                    raise ValueError(
                        "linked transcript target must be another document item"
                    )
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("transcript limitations must be unique")
        if self.manifest_id == self.clean_artifact_id:
            raise ValueError("manifest and clean artifact ids must be distinct")
        return self


class TranscriptReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: OpaqueId
    title: str = Field(min_length=1, max_length=500)
    status: TranscriptReviewStatus
    total_documents: int = Field(ge=0, le=MAX_COUNT)
    total_items: int = Field(ge=0, le=MAX_COUNT)
    pending_items: int = Field(ge=0, le=MAX_COUNT)
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
        document_ids = [
            str(document.document_id) for document in self.documents
        ]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("transcript document ids must be unique")
        return self
