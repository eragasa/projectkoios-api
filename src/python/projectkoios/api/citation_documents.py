from __future__ import annotations

from typing import BinaryIO, Protocol

from projectkoios.api.citation_document_models import (
    CitationDocumentCatalogResponse,
    CitationDocumentProcessRequest,
    CitationDocumentProcessResponse,
    CitationDocumentReceiptResponse,
)
from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
)


class CitationDocumentNotFound(ProjectionNotFound):
    """The owner has no citation-document projection for an opaque identity."""


class CitationDocumentUnavailable(ProviderUnavailable):
    """The citation-document owner cannot currently serve control state."""


class InvalidCitationDocumentRequest(ValueError):
    """The request is bounded but invalid for the current owner projection."""


class CitationDocumentProjectionConflict(ValueError):
    """The request conflicts with the current immutable owner projection."""


class CitationDocumentPdfTooLarge(ValueError):
    """The uploaded PDF exceeds the exact application custody bound."""


class CitationDocumentProvider(Protocol):
    """Path-free port implemented by the citation-document application owner."""

    def read_catalog(self) -> CitationDocumentCatalogResponse: ...

    def receive_source(
        self,
        item_id: str,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceiptResponse: ...

    def process_private(
        self,
        item_id: str,
        request: CitationDocumentProcessRequest,
    ) -> CitationDocumentProcessResponse: ...

    def read_transcript_collection(self) -> TranscriptCollectionResponse: ...

    def read_transcript(
        self, document_id: str
    ) -> TranscriptDocumentResponse: ...


class CitationDocumentTranscriptProvider:
    """Expose only the existing transcript port from a citation owner."""

    def __init__(self, provider: CitationDocumentProvider) -> None:
        self._provider = provider

    def read_collection(self) -> TranscriptCollectionResponse:
        return self._provider.read_transcript_collection()

    def read_document(self, document_id: str) -> TranscriptDocumentResponse:
        return self._provider.read_transcript(document_id)
