from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewQueueResponse,
)


class TranscriptReviewUnavailable(ProviderUnavailable):
    """The transcript owner cannot currently project review state."""


class TranscriptReviewNotFound(ProjectionNotFound):
    """The transcript owner has no projection for an opaque identifier."""


@dataclass(frozen=True)
class TranscriptReviewResource:
    """Path-free bounded binary resource returned by an owner adapter."""

    body: bytes
    media_type: str


class TranscriptReviewProvider(Protocol):
    """Narrow port implemented by the transcript domain owner."""

    def read_queue(self) -> TranscriptReviewQueueResponse: ...

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse: ...

    def read_source(self, document_id: str) -> TranscriptReviewResource: ...

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource: ...
