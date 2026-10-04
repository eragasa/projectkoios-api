from __future__ import annotations

import re
from typing import Annotated, Literal

from projectkoios.api.project_reference_intake import (
    ProjectPdfBindingDisposition,
    ProjectPdfProvisionStatus,
    ProjectPdfReceiptDisposition,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_HASH_LIKE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", re.I)
Citekey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}$",
    ),
]


class MissingPdfItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citekey: Citekey
    entry_type: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
    )
    title: str | None = Field(default=None, min_length=1, max_length=2_000)
    authors: tuple[str, ...] = Field(max_length=100)
    year: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("title", "year")
    @classmethod
    def safe_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            cls._require_safe_text(value)
        return value

    @field_validator("authors")
    @classmethod
    def safe_authors(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not 1 <= len(value) <= 500 for value in values):
            raise ValueError("authors contain an invalid display length")
        for value in values:
            cls._require_safe_text(value)
        return values

    @staticmethod
    def _require_safe_text(value: str) -> None:
        if (
            _CONTROL_CHARACTER.search(value) is not None
            or "sha256" in value.casefold()
            or _HASH_LIKE.search(value) is not None
            or "/Users/" in value
            or "\\Users\\" in value
        ):
            raise ValueError("display text contains private integrity metadata")


class MissingPdfListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: Literal["ksdft2effmass"] = "ksdft2effmass"
    total_references: int = Field(ge=0, le=10_000)
    required_pdf_count: int = Field(ge=0, le=10_000)
    bound_pdf_count: int = Field(ge=0, le=10_000)
    missing_pdf_count: int = Field(ge=0, le=10_000)
    not_applicable_count: int = Field(ge=0, le=10_000)
    max_pdf_bytes: int = Field(ge=1, le=100_000_000)
    media_type: Literal["application/pdf"] = "application/pdf"
    items: tuple[MissingPdfItemResponse, ...] = Field(max_length=10_000)

    @model_validator(mode="after")
    def consistent_counts(self) -> MissingPdfListResponse:
        if self.missing_pdf_count != len(self.items):
            raise ValueError("missing count must match items")
        if self.required_pdf_count != (
            self.bound_pdf_count + self.missing_pdf_count
        ):
            raise ValueError("required count must match bound and missing")
        if self.total_references != (
            self.required_pdf_count + self.not_applicable_count
        ):
            raise ValueError("total count must match requirement counts")
        citekeys = [item.citekey for item in self.items]
        if citekeys != sorted(set(citekeys)):
            raise ValueError("missing citekeys must be unique and ordered")
        return self


class ProvideMissingPdfResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: Literal["ksdft2effmass"] = "ksdft2effmass"
    citekey: Citekey
    byte_size: int = Field(ge=1, le=100_000_000)
    receipt_disposition: ProjectPdfReceiptDisposition
    binding_disposition: ProjectPdfBindingDisposition
    document_status: Literal["received-unreviewed"] = "received-unreviewed"


class ReceivedUnboundPdfResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: Literal["ksdft2effmass"] = "ksdft2effmass"
    citekey: Citekey
    byte_size: int = Field(ge=1, le=100_000_000)
    receipt_disposition: ProjectPdfReceiptDisposition
    binding_status: Literal[ProjectPdfProvisionStatus.RECEIVED_UNBOUND] = (
        ProjectPdfProvisionStatus.RECEIVED_UNBOUND
    )
    document_status: Literal["received-unreviewed"] = "received-unreviewed"
    detail: Literal["PDF was received but could not be bound"] = (
        "PDF was received but could not be bound"
    )
