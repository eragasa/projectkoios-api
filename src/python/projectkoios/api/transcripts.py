from __future__ import annotations

from typing import Protocol

from projectkoios.api.config import TranscriptConfiguration
from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
    TranscriptDocumentSummaryResponse,
)


class TranscriptNotFound(ProjectionNotFound):
    """No configured transcript has the requested opaque identity."""


class TranscriptUnavailable(ProviderUnavailable):
    """The configured transcript owner cannot currently project its state."""


class TranscriptProvider(Protocol):
    """Path-free read port consumed by the HTTP transcript surface."""

    def read_collection(self) -> TranscriptCollectionResponse: ...

    def read_document(self, document_id: str) -> TranscriptDocumentResponse: ...


class TranscriptOwner(Protocol):
    """Applications-owned projection for one explicitly configured document."""

    def project_document(self) -> TranscriptDocumentResponse: ...


class TranscriptRepository:
    """Map one explicit owner root to collection and identity-based reads."""

    def __init__(
        self,
        configuration: TranscriptConfiguration,
        *,
        owner: TranscriptOwner | None = None,
    ) -> None:
        self._configuration = configuration
        self._owner = owner

    def read_collection(self) -> TranscriptCollectionResponse:
        if self._configuration.document_root is None:
            return TranscriptCollectionResponse(documents=())
        document = self._project_document()
        return TranscriptCollectionResponse(
            documents=(
                TranscriptDocumentSummaryResponse.model_validate(
                    document.model_dump(exclude={"pages"}),
                    strict=True,
                ),
            )
        )

    def read_document(self, document_id: str) -> TranscriptDocumentResponse:
        if self._configuration.document_root is None:
            raise TranscriptNotFound(document_id)
        document = self._project_document()
        if document.document_id != document_id:
            raise TranscriptNotFound(document_id)
        return document

    def _project_document(self) -> TranscriptDocumentResponse:
        if self._owner is None:
            raise TranscriptUnavailable
        return self._owner.project_document()
