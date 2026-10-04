from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, final

from projectkoios.api.project_reference_intake import (
    ProjectMissingPdf,
    ProjectMissingPdfList,
    ProjectPdfBindingDisposition,
    ProjectPdfProvisionStatus,
    ProjectPdfReceiptDisposition,
    ProjectProvidedPdf,
    ProjectReferenceIntakeInvalidPdf,
    ProjectReferenceIntakeMalformed,
    ProjectReferenceIntakeNotFound,
    ProjectReferenceIntakePdfTooLarge,
    ProjectReferenceIntakeUnavailable,
)
from projectkoios.references.adapters.bibliography import (
    pybtex_metadata_reader,
)
from projectkoios.references.adapters.filesystem import (
    sha256_pdf_object_store,
)
from projectkoios.references.adapters.sql.sqlite import (
    document_reference_store,
)
from projectkoios.references.document_reference.bibliography.metadata.errors import (  # noqa: E501
    BibliographyMetadataError,
)
from projectkoios.references.document_reference.bindings.explicit.action import (  # noqa: E501
    BindPdfToReference,
)
from projectkoios.references.document_reference.collections.errors import (
    UnknownCollection,
    UnknownReference,
)
from projectkoios.references.document_reference.collections.missing.action import (  # noqa: E501
    ListMissingPdfReferences,
)
from projectkoios.references.document_reference.collections.missing.request import (  # noqa: E501
    ListMissingPdfReferencesRequest,
)
from projectkoios.references.document_reference.documents.errors import (
    DocumentContentConflict,
    UnknownDocument,
)
from projectkoios.references.document_reference.documents.receipt.action import (  # noqa: E501
    ReceivePdf,
)
from projectkoios.references.document_reference.documents.receipt.disposition import (  # noqa: E501
    PdfReceiptDisposition,
)
from projectkoios.references.document_reference.documents.receipt.errors import (  # noqa: E501
    InvalidPdfUpload,
    PdfUploadTooLarge,
)
from projectkoios.references.document_reference.errors import (
    DocumentReferenceStoreError,
)
from projectkoios.references.document_reference.intake.action import (
    ProvideReferencePdf,
)
from projectkoios.references.document_reference.intake.request import (
    ProvideReferencePdfRequest,
)
from projectkoios.references.document_reference.intake.status import (
    ReferencePdfProvisionStatus,
)
from projectkoios.references.path_safety.preflight import RootStorageClass
from projectkoios.references.path_safety.root import AuthorizedRoot

_COLLECTION_ID = "ksdft2effmass"


@final
class ConfiguredProjectReferenceIntakeOwner:
    """Compose References-owned operations for one local project collection."""

    __slots__ = ("_list_missing", "_max_pdf_bytes", "_provide")

    def __init__(
        self,
        *,
        database_root: Path,
        database_name: str,
        object_root: Path,
        max_pdf_bytes: int,
    ) -> None:
        try:
            database_capability = AuthorizedRoot.create(
                database_root.expanduser(),
                label="document/reference database root",
                root_alias="document-reference-database",
                storage_class=RootStorageClass.LOCAL,
            )
            object_capability = AuthorizedRoot.create(
                object_root.expanduser(),
                label="reference PDF object root",
                root_alias="reference-pdf-objects",
                storage_class=RootStorageClass.LOCAL,
            )
            repository = document_reference_store.SqliteDocumentReferenceStore(
                database_root=database_capability,
                database_name=database_name,
                metadata_reader=(
                    pybtex_metadata_reader.PybtexBibliographyMetadataReader()
                ),
            )
            objects = sha256_pdf_object_store.Sha256PdfObjectStore(
                root=object_capability,
                max_pdf_bytes=max_pdf_bytes,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ProjectReferenceIntakeUnavailable from error
        self._max_pdf_bytes = max_pdf_bytes
        self._list_missing = ListMissingPdfReferences(repository=repository)
        receive = ReceivePdf(objects=objects, repository=repository)
        self._provide = ProvideReferencePdf(
            receive=receive,
            bind=BindPdfToReference(repository=repository),
        )

    @property
    def max_pdf_bytes(self) -> int:
        return self._max_pdf_bytes

    def missing_pdfs(self) -> ProjectMissingPdfList:
        try:
            owner = self._list_missing.action(
                request=ListMissingPdfReferencesRequest(
                    collection_id=_COLLECTION_ID
                )
            )
            return ProjectMissingPdfList(
                collection_id=owner.collection_id,
                required_count=owner.required_count,
                bound_count=owner.bound_count,
                not_applicable_count=owner.not_applicable_count,
                missing=tuple(
                    ProjectMissingPdf(
                        citekey=item.citekey,
                        entry_type=item.entry_type,
                        title=item.title,
                        authors=item.authors,
                        year=item.year,
                    )
                    for item in owner.missing
                ),
            )
        except UnknownCollection as error:
            raise ProjectReferenceIntakeNotFound from error
        except BibliographyMetadataError as error:
            raise ProjectReferenceIntakeMalformed from error
        except (DocumentReferenceStoreError, OSError) as error:
            raise ProjectReferenceIntakeUnavailable from error
        except (TypeError, ValueError) as error:
            raise ProjectReferenceIntakeMalformed from error

    def provide_pdf(
        self,
        *,
        citekey: str,
        stream: BinaryIO,
        declared_byte_size: int,
    ) -> ProjectProvidedPdf:
        try:
            provision = self._provide.provide(
                request=ProvideReferencePdfRequest(
                    collection_id=_COLLECTION_ID,
                    citekey=citekey,
                    declared_byte_size=declared_byte_size,
                ),
                stream=stream,
            )
            binding_disposition = (
                None
                if provision.binding is None
                else ProjectPdfBindingDisposition(
                    provision.binding.disposition.value
                )
            )
            return ProjectProvidedPdf(
                citekey=citekey,
                byte_size=provision.receipt.byte_size,
                receipt_disposition=self._receipt_disposition(
                    provision.receipt.disposition
                ),
                provision_status=self._provision_status(provision.status),
                binding_disposition=binding_disposition,
            )
        except PdfUploadTooLarge as error:
            raise ProjectReferenceIntakePdfTooLarge from error
        except InvalidPdfUpload as error:
            raise ProjectReferenceIntakeInvalidPdf from error
        except (UnknownCollection, UnknownReference, UnknownDocument) as error:
            raise ProjectReferenceIntakeNotFound from error
        except DocumentContentConflict as error:
            raise ProjectReferenceIntakeUnavailable from error
        except (DocumentReferenceStoreError, OSError) as error:
            raise ProjectReferenceIntakeUnavailable from error
        except (TypeError, ValueError) as error:
            raise ProjectReferenceIntakeMalformed from error

    @staticmethod
    def _receipt_disposition(
        value: PdfReceiptDisposition,
    ) -> ProjectPdfReceiptDisposition:
        return ProjectPdfReceiptDisposition(value.value)

    @staticmethod
    def _provision_status(
        value: ReferencePdfProvisionStatus,
    ) -> ProjectPdfProvisionStatus:
        return ProjectPdfProvisionStatus(value.value)
