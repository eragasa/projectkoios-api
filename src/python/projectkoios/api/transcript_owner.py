from __future__ import annotations

from pathlib import Path

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.provider_boundary import MalformedProviderProjection
from projectkoios.api.transcript_models import (
    TranscriptDocumentResponse,
    TranscriptPageResponse,
    TranscriptStatus,
)
from projectkoios.api.transcripts import TranscriptUnavailable
from projectkoios.applications.pdf_corpus_ingestion import (
    DOCUMENT_TRANSCRIPT_CONTRACT_ID as OWNER_CONTRACT_ID,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DOCUMENT_TRANSCRIPT_SCHEMA_VERSION as OWNER_SCHEMA_VERSION,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    MAX_DOCUMENT_TRANSCRIPT_DISPLAY_NAME_BYTES as OWNER_MAX_DISPLAY_NAME_BYTES,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptError as OwnerTranscriptError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptIncompleteError as OwnerIncompleteError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptMalformedError as OwnerMalformedError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptPage as OwnerTranscriptPage,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptProjection as OwnerTranscriptProjection,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptStatus as OwnerTranscriptStatus,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    DocumentTranscriptUnavailableError as OwnerUnavailableError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    project_document_transcript,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass
from pydantic import ValidationError

_EXPECTED_CONTRACT_ID = (
    "projectkoios.applications.pdf-corpus-document-transcript"
)
_EXPECTED_SCHEMA_VERSION = 1
_EXPECTED_MAX_DISPLAY_NAME_BYTES = 1_024


class ApplicationsTranscriptOwner:
    """Adapt the Applications-owned exact transcript projection."""

    def __init__(self, document_root: Path) -> None:
        self._document_root = document_root.expanduser()

    def project_document(self) -> TranscriptDocumentResponse:
        _require_owner_contract()
        try:
            projection = project_document_transcript(document_root=self._root())
        except OwnerIncompleteError as error:
            raise TranscriptUnavailable from error
        except OwnerUnavailableError as error:
            raise TranscriptUnavailable from error
        except OwnerMalformedError as error:
            raise MalformedProviderProjection from error
        except OwnerTranscriptError as error:
            raise MalformedProviderProjection from error
        try:
            return _response(projection)
        except (TypeError, ValueError, ValidationError) as error:
            raise MalformedProviderProjection from error

    def _root(self) -> AuthorizedRoot:
        try:
            return AuthorizedRoot.existing(
                self._document_root,
                label="configured transcript document",
                root_alias="transcript-document",
                storage_class=RootStorageClass.LOCAL,
            )
        except (OSError, ValueError) as error:
            raise TranscriptUnavailable from error


def _require_owner_contract() -> None:
    if (
        OWNER_CONTRACT_ID != _EXPECTED_CONTRACT_ID
        or OWNER_SCHEMA_VERSION != _EXPECTED_SCHEMA_VERSION
        or OWNER_MAX_DISPLAY_NAME_BYTES != _EXPECTED_MAX_DISPLAY_NAME_BYTES
    ):
        raise TranscriptUnavailable


def _response(projection: object) -> TranscriptDocumentResponse:
    if not isinstance(projection, OwnerTranscriptProjection):
        raise TypeError("owner transcript projection type is invalid")
    if (
        projection.contract_id != OWNER_CONTRACT_ID
        or projection.schema_version != OWNER_SCHEMA_VERSION
        or projection.status is not OwnerTranscriptStatus.AUTOMATED_UNREVIEWED
    ):
        raise ValueError("owner transcript contract is inconsistent")
    pages = tuple(_page(page) for page in projection.pages)
    return TranscriptDocumentResponse(
        document_id=OpaqueId(projection.document_id),
        display_name=projection.display_name,
        status=TranscriptStatus.AUTOMATED_UNREVIEWED,
        physical_page_count=projection.physical_page_count,
        pages=pages,
    )


def _page(page: object) -> TranscriptPageResponse:
    if not isinstance(page, OwnerTranscriptPage):
        raise TypeError("owner transcript page type is invalid")
    return TranscriptPageResponse(
        page_id=OpaqueId(page.page_id),
        page_index=page.page_index,
        physical_page=page.physical_page,
        printed_page_label=page.printed_page_label,
        text=page.text,
    )
