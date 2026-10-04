from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, Protocol


class ProjectReferenceIntakeError(RuntimeError):
    """Base failure for the project reference-intake boundary."""


class ProjectReferenceIntakeNotFound(ProjectReferenceIntakeError):
    """The project collection or selected reference is absent."""


class ProjectReferenceIntakeInvalidPdf(ProjectReferenceIntakeError):
    """The supplied body is not an acceptable PDF."""


class ProjectReferenceIntakePdfTooLarge(ProjectReferenceIntakeInvalidPdf):
    """The supplied body exceeds the configured PDF cap."""


class ProjectReferenceIntakeMalformed(ProjectReferenceIntakeError):
    """The owner returned malformed or inconsistent state."""


class ProjectReferenceIntakeUnavailable(ProjectReferenceIntakeError):
    """The owner store is unavailable."""


class ProjectPdfReceiptDisposition(StrEnum):
    RECEIVED = "received"
    SOURCE_OBSERVATION_ADDED = "source-observation-added"
    ALREADY_PRESENT = "already-present"


class ProjectPdfBindingDisposition(StrEnum):
    BOUND = "bound"
    ALREADY_BOUND = "already-bound"


class ProjectPdfProvisionStatus(StrEnum):
    BOUND = "bound"
    ALREADY_BOUND = "already-bound"
    RECEIVED_UNBOUND = "received-unbound"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectMissingPdf:
    citekey: str
    entry_type: str
    title: str | None
    authors: tuple[str, ...]
    year: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectMissingPdfList:
    collection_id: str
    required_count: int
    bound_count: int
    not_applicable_count: int
    missing: tuple[ProjectMissingPdf, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectProvidedPdf:
    citekey: str
    byte_size: int
    receipt_disposition: ProjectPdfReceiptDisposition
    provision_status: ProjectPdfProvisionStatus
    binding_disposition: ProjectPdfBindingDisposition | None

    def __post_init__(self) -> None:
        expected = {
            ProjectPdfProvisionStatus.BOUND: ProjectPdfBindingDisposition.BOUND,
            ProjectPdfProvisionStatus.ALREADY_BOUND: (
                ProjectPdfBindingDisposition.ALREADY_BOUND
            ),
            ProjectPdfProvisionStatus.RECEIVED_UNBOUND: None,
        }[self.provision_status]
        if self.binding_disposition is not expected:
            raise ValueError(
                "provision status does not match binding disposition"
            )


class ProjectReferenceIntakeProvider(Protocol):
    @property
    def max_pdf_bytes(self) -> int: ...

    def missing_pdfs(self) -> ProjectMissingPdfList: ...

    def provide_pdf(
        self,
        *,
        citekey: str,
        stream: BinaryIO,
        declared_byte_size: int,
    ) -> ProjectProvidedPdf: ...


class UnavailableProjectReferenceIntakeProvider:
    @property
    def max_pdf_bytes(self) -> int:
        return 100_000_000

    def missing_pdfs(self) -> ProjectMissingPdfList:
        raise ProjectReferenceIntakeUnavailable

    def provide_pdf(
        self,
        *,
        citekey: str,
        stream: BinaryIO,
        declared_byte_size: int,
    ) -> ProjectProvidedPdf:
        del citekey, stream, declared_byte_size
        raise ProjectReferenceIntakeUnavailable
