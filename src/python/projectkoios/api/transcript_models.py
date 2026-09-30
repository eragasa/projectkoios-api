from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from projectkoios.api.boundary_models import OpaqueId
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_TRANSCRIPT_DOCUMENTS = 1
MAX_TRANSCRIPT_PAGES = 10_000
MAX_TRANSCRIPT_PAGE_TEXT_LENGTH = 1_000_000
MAX_TRANSCRIPT_TEXT_LENGTH = 10_000_000

TranscriptDisplayName = Annotated[str, Field(min_length=1, max_length=1024)]
TranscriptPageText = Annotated[
    str,
    Field(
        max_length=MAX_TRANSCRIPT_PAGE_TEXT_LENGTH,
        description=(
            "Exact owner-supplied parsed page transcript, including whitespace "
            "and newlines. Empty text is valid."
        ),
    ),
]


class TranscriptStatus(StrEnum):
    AUTOMATED_UNREVIEWED = "AUTOMATED_UNREVIEWED"


class TranscriptDocumentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: OpaqueId
    display_name: TranscriptDisplayName
    status: TranscriptStatus
    physical_page_count: int = Field(ge=1, le=MAX_TRANSCRIPT_PAGES)


class TranscriptPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: OpaqueId
    page_index: int = Field(ge=0, lt=MAX_TRANSCRIPT_PAGES)
    physical_page: int = Field(ge=1, le=MAX_TRANSCRIPT_PAGES)
    printed_page_label: str | None = Field(
        min_length=1,
        max_length=100,
    )
    text: TranscriptPageText


class TranscriptDocumentResponse(TranscriptDocumentSummaryResponse):
    pages: tuple[TranscriptPageResponse, ...] = Field(
        min_length=1,
        max_length=MAX_TRANSCRIPT_PAGES,
        description=(
            "Complete authoritative owner page order. Page indexes are "
            "contiguous and zero-based."
        ),
    )

    @model_validator(mode="after")
    def has_complete_ordered_pages(self) -> TranscriptDocumentResponse:
        if self.physical_page_count != len(self.pages):
            raise ValueError("transcript page count must match the detail")
        page_ids: set[str] = set()
        total_text_length = 0
        for expected_index, page in enumerate(self.pages):
            if page.page_index != expected_index:
                raise ValueError(
                    "transcript page indexes must be contiguous and ordered"
                )
            if page.physical_page != expected_index + 1:
                raise ValueError(
                    "transcript physical pages must be one-based and ordered"
                )
            page_id = str(page.page_id)
            if page_id in page_ids:
                raise ValueError("transcript page ids must be unique")
            page_ids.add(page_id)
            total_text_length += len(page.text)
        if total_text_length > MAX_TRANSCRIPT_TEXT_LENGTH:
            raise ValueError("transcript text exceeds the document limit")
        return self


class TranscriptCollectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: tuple[TranscriptDocumentSummaryResponse, ...] = Field(
        max_length=MAX_TRANSCRIPT_DOCUMENTS,
        description="Configured documents in authoritative owner order.",
    )

    @model_validator(mode="after")
    def has_unique_documents(self) -> TranscriptCollectionResponse:
        document_ids = [
            str(document.document_id) for document in self.documents
        ]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("transcript document ids must be unique")
        return self
