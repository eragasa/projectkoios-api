from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from projectkoios.api.boundary_models import OpaqueId
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

MAX_CITATION_DOCUMENT_ITEMS = 10_000
MAX_CITATION_DOCUMENT_OCCURRENCES = 10_000
MAX_CITATION_DOCUMENT_SOURCE_DOCUMENTS = 10_000
MAX_CITATION_DOCUMENT_LINKS = 20_000
MAX_CITATION_DOCUMENT_SOURCE_GAPS = 10_000
MAX_CITATION_DOCUMENT_IDS_PER_ITEM = 256
MAX_CITATION_DOCUMENT_ID_BYTES = 4_096
MAX_CITATION_DOCUMENT_TEXT_BYTES = 4_096
MAX_CITATION_DOCUMENT_SOURCE_PATH_BYTES = 4_096
MAX_CITATION_DOCUMENT_PDF_BYTES = 50_000_000
MAX_CITATION_DOCUMENT_DESCRIPTOR_BYTES = 100_000_000
MAX_CITATION_DOCUMENT_PAGES = 10_000

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SHA256 = re.compile(_SHA256_PATTERN)

Sha256 = Annotated[
    str,
    Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN),
]
BoundedText = Annotated[str, Field(min_length=1, max_length=4_096)]


def _validated_owner_id(value: str) -> str:
    """Retain a bounded owner identity verbatim without making it a path."""

    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("owner identity must be UTF-8 encodable") from error
    if (
        value != value.strip()
        or len(encoded) > MAX_CITATION_DOCUMENT_ID_BYTES
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        raise ValueError("owner identity is malformed")
    return value


OwnerOpaqueId = Annotated[
    str,
    Field(min_length=1, max_length=MAX_CITATION_DOCUMENT_ID_BYTES),
    AfterValidator(_validated_owner_id),
]


class CitationBibliographyMembershipStatus(StrEnum):
    DEFINED = "defined"
    UNDEFINED = "undefined"
    NOT_EVALUATED = "not-evaluated"


class CitationKeyResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class CitationIdentityStatus(StrEnum):
    ACCEPTED_ACTIVE_CANONICAL = "accepted-active-canonical"
    ACCEPTED_WITHOUT_ACTIVE_CITEKEY = "accepted-without-active-citekey"
    CANDIDATE_PROPOSED_NONCANONICAL = "candidate-proposed-noncanonical"
    INACTIVE_SUPERSEDED = "inactive-superseded"
    UNRESOLVED = "unresolved"


class CitationDocumentAvailabilityStatus(StrEnum):
    NOT_EVALUATED = "not-evaluated"
    NOT_OBSERVED = "not-observed"
    AVAILABLE_UNVERIFIED_LINKAGE = "available-unverified-linkage"
    AVAILABLE_LINKED = "available-linked"
    AMBIGUOUS = "ambiguous"
    INACCESSIBLE = "inaccessible"


class CitationDocumentTerminalStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class CitationDocumentFailureCode(StrEnum):
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    PACKAGE_BUILD_FAILED = "PACKAGE_BUILD_FAILED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    PUBLICATION_INDETERMINATE = "PUBLICATION_INDETERMINATE"
    TRANSCRIPT_VERIFICATION_FAILED = "TRANSCRIPT_VERIFICATION_FAILED"


class CitationDocumentApiErrorCode(StrEnum):
    INVALID_REQUEST = "CITATION_DOCUMENT_INVALID_REQUEST"
    ITEM_NOT_FOUND = "CITATION_DOCUMENT_ITEM_NOT_FOUND"
    PROJECTION_CONFLICT = "CITATION_DOCUMENT_PROJECTION_CONFLICT"
    PDF_TOO_LARGE = "CITATION_DOCUMENT_PDF_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "CITATION_DOCUMENT_UNSUPPORTED_MEDIA_TYPE"
    OWNER_MALFORMED = "CITATION_DOCUMENT_OWNER_MALFORMED"
    OWNER_UNAVAILABLE = "CITATION_DOCUMENT_OWNER_UNAVAILABLE"
    OWNER_FAILURE = "CITATION_DOCUMENT_OWNER_FAILURE"


class CitationDocumentApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CitationDocumentApiErrorCode
    detail: str = Field(min_length=1, max_length=500)


class CitationDocumentApiErrorEnvelope(BaseModel):
    """FastAPI HTTPException envelope containing a stable feature error."""

    model_config = ConfigDict(extra="forbid")

    detail: CitationDocumentApiErrorResponse


class CitationContentIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str = Field(pattern=r"^sha256$")
    digest: Sha256
    byte_count: int = Field(ge=1, le=100_000_000)


class CitationSourceLocatorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(
        min_length=1, max_length=MAX_CITATION_DOCUMENT_SOURCE_PATH_BYTES
    )
    source_content_identity: CitationContentIdentityResponse
    include_index: int = Field(ge=0, lt=MAX_CITATION_DOCUMENT_OCCURRENCES)
    byte_start: int = Field(ge=0, le=100_000_000)
    byte_end: int = Field(gt=0, le=100_000_000)
    line: int = Field(ge=1, le=1_000_000_000)
    column: int = Field(ge=1, le=1_000_000_000)

    @model_validator(mode="after")
    def has_safe_consistent_location(self) -> CitationSourceLocatorResponse:
        path_bytes = self.source_path.encode("utf-8")
        parts = self.source_path.split("/")
        if (
            len(path_bytes) > MAX_CITATION_DOCUMENT_SOURCE_PATH_BYTES
            or self.source_path.startswith("/")
            or "\\" in self.source_path
            or "\x00" in self.source_path
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError(
                "citation source path must be normalized and relative"
            )
        if self.byte_end <= self.byte_start:
            raise ValueError(
                "citation source byte range must have positive length"
            )
        if self.byte_end > self.source_content_identity.byte_count:
            raise ValueError("citation source byte range exceeds its source")
        return self


class CitationSourceGapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_gap_id: OwnerOpaqueId
    source_gap_index: int = Field(ge=0, lt=MAX_CITATION_DOCUMENT_SOURCE_GAPS)
    locator: CitationSourceLocatorResponse
    reason: str = Field(pattern=r"^placeholder_identifier$")
    placeholder_identifier: BoundedText


class CitationIdentityItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: OwnerOpaqueId
    requested_identity_id: OwnerOpaqueId
    projection_id: OwnerOpaqueId
    status: CitationIdentityStatus
    reference_id: OwnerOpaqueId | None = None
    canonical_citekey: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    proposed_citekey: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    successor_reference_ids: tuple[OwnerOpaqueId, ...] = Field(
        default=(), max_length=MAX_CITATION_DOCUMENT_IDS_PER_ITEM
    )


class CitationSourceDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: OwnerOpaqueId
    sha256: Sha256
    byte_size: int = Field(ge=1, le=MAX_CITATION_DOCUMENT_DESCRIPTOR_BYTES)
    media_type: str = Field(pattern=r"^application/pdf$")
    descriptor_id: OwnerOpaqueId


class CitationDocumentItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: OpaqueId
    target_snapshot_id: OwnerOpaqueId
    identity_projection_id: OwnerOpaqueId
    literal_citekey: str = Field(
        min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$"
    )
    occurrence_ids: tuple[OwnerOpaqueId, ...] = Field(
        min_length=1,
        max_length=MAX_CITATION_DOCUMENT_OCCURRENCES,
    )
    bibliography_membership_status: CitationBibliographyMembershipStatus
    key_resolution_status: CitationKeyResolutionStatus
    identity_items: tuple[CitationIdentityItemResponse, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_ITEMS
    )
    document_status: CitationDocumentAvailabilityStatus
    source_document_ids: tuple[OwnerOpaqueId, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_IDS_PER_ITEM
    )
    source_document_link_ids: tuple[OwnerOpaqueId, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_IDS_PER_ITEM
    )

    @model_validator(mode="after")
    def has_consistent_owner_states(self) -> CitationDocumentItemResponse:
        if len(self.occurrence_ids) != len(set(self.occurrence_ids)):
            raise ValueError("citation occurrence identities must be unique")
        requested = [
            str(item.requested_identity_id) for item in self.identity_items
        ]
        if requested != sorted(set(requested)):
            raise ValueError("citation identity items must be canonical")
        if any(
            item.projection_id != self.identity_projection_id
            for item in self.identity_items
        ):
            raise ValueError("citation identity item projection conflicts")
        if self.key_resolution_status is CitationKeyResolutionStatus.RESOLVED:
            if len(self.identity_items) != 1 or self.identity_items[
                0
            ].status not in {
                CitationIdentityStatus.ACCEPTED_ACTIVE_CANONICAL,
                CitationIdentityStatus.CANDIDATE_PROPOSED_NONCANONICAL,
            }:
                raise ValueError("resolved citation identity items are invalid")
        elif (
            self.key_resolution_status is CitationKeyResolutionStatus.AMBIGUOUS
        ):
            if len(self.identity_items) < 2 or any(
                item.status
                is not CitationIdentityStatus.CANDIDATE_PROPOSED_NONCANONICAL
                for item in self.identity_items
            ):
                raise ValueError(
                    "ambiguous citation identity items are invalid"
                )
        elif self.identity_items:
            raise ValueError(
                "unresolved citation key cannot carry identity items"
            )
        for values in (self.source_document_ids, self.source_document_link_ids):
            if tuple(values) != tuple(sorted(set(values))):
                raise ValueError(
                    "citation document identities must be canonical"
                )
        if (
            self.document_status
            is CitationDocumentAvailabilityStatus.NOT_OBSERVED
            and (
                self.key_resolution_status
                is not CitationKeyResolutionStatus.RESOLVED
            )
        ):
            raise ValueError("not-observed requires a resolved identity")
        if self.document_status in {
            CitationDocumentAvailabilityStatus.NOT_EVALUATED,
            CitationDocumentAvailabilityStatus.NOT_OBSERVED,
            CitationDocumentAvailabilityStatus.INACCESSIBLE,
        } and (self.source_document_ids or self.source_document_link_ids):
            raise ValueError(
                "citation document state conflicts with identities"
            )
        if (
            self.document_status
            is CitationDocumentAvailabilityStatus.AVAILABLE_UNVERIFIED_LINKAGE
            and (not self.source_document_ids or self.source_document_link_ids)
        ):
            raise ValueError("unverified citation document linkage is invalid")
        if (
            self.document_status
            is CitationDocumentAvailabilityStatus.AVAILABLE_LINKED
            and (
                not self.source_document_ids
                or not self.source_document_link_ids
            )
        ):
            raise ValueError("linked citation document state is invalid")
        if (
            self.document_status is CitationDocumentAvailabilityStatus.AMBIGUOUS
            and not self.source_document_ids
        ):
            raise ValueError(
                "ambiguous citation document state needs documents"
            )
        return self


class CitationDocumentProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: OwnerOpaqueId
    target_snapshot_id: OwnerOpaqueId
    target_projection_id: OwnerOpaqueId
    bibliography_binding_ids: tuple[OwnerOpaqueId, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_ITEMS
    )
    identity_projection_id: OwnerOpaqueId
    document_observation_ids: tuple[OwnerOpaqueId, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_ITEMS
    )
    source_document_link_ids: tuple[OwnerOpaqueId, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_LINKS
    )
    source_documents: tuple[CitationSourceDocumentResponse, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_SOURCE_DOCUMENTS
    )
    items: tuple[CitationDocumentItemResponse, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_ITEMS
    )
    source_gaps: tuple[CitationSourceGapResponse, ...] = Field(
        max_length=MAX_CITATION_DOCUMENT_SOURCE_GAPS
    )
    limitations: tuple[BoundedText, ...] = Field(max_length=100)
    projection_id: OwnerOpaqueId

    @model_validator(mode="after")
    def has_consistent_projection(self) -> CitationDocumentProjectionResponse:
        item_keys = [item.literal_citekey for item in self.items]
        if item_keys != sorted(set(item_keys)):
            raise ValueError(
                "citation document items must use canonical key order"
            )
        item_ids = [str(item.item_id) for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("citation document item identities must be unique")
        occurrences = [
            str(value) for item in self.items for value in item.occurrence_ids
        ]
        if len(occurrences) != len(set(occurrences)):
            raise ValueError("citation document occurrences must not overlap")
        descriptors = [
            str(item.descriptor_id) for item in self.source_documents
        ]
        source_ids = [
            str(item.source_document_id) for item in self.source_documents
        ]
        if descriptors != sorted(set(descriptors)) or len(source_ids) != len(
            set(source_ids)
        ):
            raise ValueError("citation source documents must be canonical")
        known_sources = set(source_ids)
        known_links = {str(item) for item in self.source_document_link_ids}
        if any(
            not {str(value) for value in item.source_document_ids}
            <= known_sources
            or not {str(value) for value in item.source_document_link_ids}
            <= known_links
            for item in self.items
        ):
            raise ValueError("citation item document identities are unknown")
        if tuple(gap.source_gap_index for gap in self.source_gaps) != tuple(
            range(len(self.source_gaps))
        ):
            raise ValueError("citation source-gap indexes must be contiguous")
        gap_ids = [str(gap.source_gap_id) for gap in self.source_gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("citation source-gap identities must be unique")
        return self


class CitationDocumentCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: OwnerOpaqueId
    result_id: OwnerOpaqueId
    projection: CitationDocumentProjectionResponse


class CitationDocumentReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document: CitationSourceDocumentResponse
    receipt_id: OwnerOpaqueId

    @model_validator(mode="after")
    def is_within_private_custody_limit(
        self,
    ) -> CitationDocumentReceiptResponse:
        if self.source_document.byte_size > MAX_CITATION_DOCUMENT_PDF_BYTES:
            raise ValueError("citation document receipt exceeds custody limit")
        return self


class CitationDocumentProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_projection_id: OwnerOpaqueId
    identity_item_id: OwnerOpaqueId
    receipt: CitationDocumentReceiptResponse


class CitationSourceDocumentLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creating_request_id: OwnerOpaqueId
    prior_projection_id: OwnerOpaqueId
    prior_item_id: OwnerOpaqueId
    target_snapshot_id: OwnerOpaqueId
    identity_projection_id: OwnerOpaqueId
    literal_citekey: str = Field(
        min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$"
    )
    identity_item_id: OwnerOpaqueId
    requested_identity_id: OwnerOpaqueId
    source_document: CitationSourceDocumentResponse
    availability_observation_ids: tuple[OwnerOpaqueId, ...] = Field(
        min_length=1,
        max_length=MAX_CITATION_DOCUMENT_IDS_PER_ITEM,
    )
    pre_effect_intent_id: OwnerOpaqueId
    linkage_basis: str = Field(
        pattern=r"^explicit-upload-for-requested-citation$"
    )
    limitations: tuple[BoundedText, ...] = Field(max_length=100)
    link_id: OwnerOpaqueId


class CitationDocumentProcessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: OwnerOpaqueId
    intent_id: OwnerOpaqueId
    link_result_id: OwnerOpaqueId
    source_document_link: CitationSourceDocumentLinkResponse
    receipt_id: OwnerOpaqueId
    source_document_descriptor_id: OwnerOpaqueId
    document_id: OpaqueId
    status: CitationDocumentTerminalStatus
    failure_code: CitationDocumentFailureCode | None = None
    extraction_bundle_id: OwnerOpaqueId | None = None
    package_id: OwnerOpaqueId | None = None
    transcript_projection_id: OwnerOpaqueId | None = None
    physical_page_count: int | None = Field(
        default=None, ge=1, le=MAX_CITATION_DOCUMENT_PAGES
    )
    publication_action: str | None = Field(
        default=None, pattern=r"^(create|unchanged)$"
    )
    result_id: OwnerOpaqueId

    @model_validator(mode="after")
    def has_terminal_evidence(self) -> CitationDocumentProcessResponse:
        readiness = (
            self.extraction_bundle_id,
            self.package_id,
            self.transcript_projection_id,
            self.physical_page_count,
            self.publication_action,
        )
        if self.status is CitationDocumentTerminalStatus.SUCCEEDED:
            if self.failure_code is not None or any(
                value is None for value in readiness
            ):
                raise ValueError(
                    "successful citation processing evidence is incomplete"
                )
        elif self.failure_code is None or any(
            value is not None for value in readiness
        ):
            raise ValueError(
                "non-success citation processing must not claim readiness"
            )
        return self
