from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.citation_document_models import (
    CitationBibliographyMembershipStatus,
    CitationContentIdentityResponse,
    CitationDocumentAvailabilityStatus,
    CitationDocumentCatalogResponse,
    CitationDocumentFailureCode,
    CitationDocumentItemResponse,
    CitationDocumentProcessRequest,
    CitationDocumentProcessResponse,
    CitationDocumentProjectionResponse,
    CitationDocumentReceiptResponse,
    CitationDocumentTerminalStatus,
    CitationIdentityItemResponse,
    CitationIdentityStatus,
    CitationKeyResolutionStatus,
    CitationSourceDocumentLinkResponse,
    CitationSourceDocumentResponse,
    CitationSourceGapResponse,
    CitationSourceLocatorResponse,
)
from projectkoios.api.citation_documents import (
    CitationDocumentNotFound,
    CitationDocumentPdfTooLarge,
    CitationDocumentProjectionConflict,
    CitationDocumentUnavailable,
    InvalidCitationDocumentRequest,
)
from projectkoios.api.provider_boundary import MalformedProviderProjection
from projectkoios.api.transcript_models import (
    TranscriptCollectionResponse,
    TranscriptDocumentResponse,
    TranscriptDocumentSummaryResponse,
    TranscriptPageResponse,
    TranscriptStatus,
)
from projectkoios.api.transcripts import (
    TranscriptNotFound,
    TranscriptUnavailable,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT,
    INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE,
    KSDFT_CITATION_TARGET_SOURCE_COMMIT,
    KSDFT_CITATION_TARGET_SOURCE_TREE,
    MAX_CITATION_DOCUMENT_PDF_BYTES,
    REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT,
    REFERENCES_CITATION_DOCUMENT_SOURCE_TREE,
    CitationDocumentCustodyError,
    CitationDocumentCustodyLimitError,
    CitationDocumentIngestionIntent,
    CitationDocumentIngestionResult,
    CitationDocumentIngestionService,
    CitationDocumentReceipt,
    CitationDocumentRegistryError,
    DocumentTranscriptPage,
    DocumentTranscriptProjection,
    DocumentTranscriptStatus,
    PrivatePdfCustody,
)
from projectkoios.ingestion import (
    PdfExtractionArtifactLimits,
    PdfExtractionConfiguration,
)
from projectkoios.references.citation_document import (
    CitationDocumentAvailabilityStatus as OwnerDocumentAvailabilityStatus,
)
from projectkoios.references.citation_document import (
    CitationDocumentProjectionItem,
    CitationDocumentProjectionRequest,
    CitationDocumentProjectionResult,
    CitationDocumentProjector,
    CitationSourceDocumentDescriptor,
)
from projectkoios.references.citations import CitationTargetSourceGap
from pydantic import ValidationError

_EXPECTED_KSDFT_COMMIT = "3ec21b4318020d700be671a8f220b2149b3d28c7"
_EXPECTED_KSDFT_TREE = "9953c0e99a28443426b5093852292f7cfbada2cc"
_EXPECTED_REFERENCES_COMMIT = "f1ca7b4aee552af131ff7af7d1408d33dd338c93"
_EXPECTED_REFERENCES_TREE = "b37672e36af13014dc25170be725fbf3f909c2d7"
_EXPECTED_INGESTION_COMMIT = "be60640bec4fe15cc88b24161545eb1027ffbd2e"
_EXPECTED_INGESTION_TREE = "d386a1744f79463fd7cd0b3087ee5fc361e0f7d5"
_EXPECTED_MAX_PDF_BYTES = 50_000_000


@dataclass(frozen=True)
class ApplicationsCitationDocumentOwner:
    """Adapt exact References and Applications owners to the HTTP ports."""

    projection_result: CitationDocumentProjectionResult
    custody: PrivatePdfCustody
    service: CitationDocumentIngestionService
    local_processing_authority_assertion_id: str
    local_processing_admission_decision_id: str
    extraction_configuration: PdfExtractionConfiguration = (
        PdfExtractionConfiguration()
    )
    artifact_limits: PdfExtractionArtifactLimits = PdfExtractionArtifactLimits()

    def __post_init__(self) -> None:
        _require_owner_contracts()
        if type(self.projection_result) is not CitationDocumentProjectionResult:
            raise TypeError(
                "projection_result must be a CitationDocumentProjectionResult"
            )
        if type(self.custody) is not PrivatePdfCustody:
            raise TypeError("custody must be a PrivatePdfCustody")
        if type(self.service) is not CitationDocumentIngestionService:
            raise TypeError(
                "service must be a CitationDocumentIngestionService"
            )
        if self.service.custody != self.custody:
            raise ValueError(
                "citation custody and ingestion service must agree"
            )
        for value, label in (
            (
                self.local_processing_authority_assertion_id,
                "local processing authority assertion",
            ),
            (
                self.local_processing_admission_decision_id,
                "local processing admission decision",
            ),
        ):
            _bounded_owner_id(value, label)
        if (
            type(self.extraction_configuration)
            is not PdfExtractionConfiguration
        ):
            raise TypeError("extraction configuration type is invalid")
        if type(self.artifact_limits) is not PdfExtractionArtifactLimits:
            raise TypeError("artifact limits type is invalid")
        try:
            self.projection_result.validate_identity()
        except (TypeError, ValueError) as error:
            raise CitationDocumentUnavailable from error

    def read_catalog(self) -> CitationDocumentCatalogResponse:
        try:
            self.projection_result.validate_identity()
            return _catalog_response(self.projection_result)
        except ValidationError as error:
            raise MalformedProviderProjection from error
        except (TypeError, ValueError) as error:
            raise CitationDocumentUnavailable from error

    def receive_source(
        self,
        item_id: str,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceiptResponse:
        self._missing_item(item_id)
        try:
            receipt = self.custody.receive(source, media_type=media_type)
            return _receipt_response(receipt)
        except CitationDocumentCustodyLimitError as error:
            raise CitationDocumentPdfTooLarge from error
        except CitationDocumentCustodyError as error:
            raise InvalidCitationDocumentRequest from error
        except ValidationError as error:
            raise MalformedProviderProjection from error

    def process_private(
        self,
        item_id: str,
        request: CitationDocumentProcessRequest,
    ) -> CitationDocumentProcessResponse:
        base_item = self._missing_item(item_id)
        projection = self.projection_result.projection
        if request.expected_projection_id != projection.projection_id:
            raise CitationDocumentProjectionConflict
        if request.identity_item_id not in {
            item.item_id for item in base_item.identity_items
        }:
            raise CitationDocumentProjectionConflict
        try:
            receipt = _receipt_from_request(request.receipt)
            projected = self._projection_with_receipt(base_item, receipt)
            projected_item = next(
                item
                for item in projected.projection.items
                if item.literal_citekey == base_item.literal_citekey
            )
            intent = CitationDocumentIngestionIntent(
                receipt=receipt,
                projection_result=projected,
                projection_item_id=projected_item.item_id,
                identity_item_id=str(request.identity_item_id),
                local_processing_authority_assertion_id=(
                    self.local_processing_authority_assertion_id
                ),
                local_processing_admission_decision_id=(
                    self.local_processing_admission_decision_id
                ),
                extraction_configuration=self.extraction_configuration,
                artifact_limits=self.artifact_limits,
            )
            owner_request = self.service.request(intent)
            result = self.service.action(request=owner_request)
            return _process_response(result)
        except CitationDocumentRegistryError as error:
            raise CitationDocumentUnavailable from error
        except CitationDocumentCustodyLimitError as error:
            raise CitationDocumentPdfTooLarge from error
        except CitationDocumentCustodyError as error:
            raise InvalidCitationDocumentRequest from error
        except InvalidCitationDocumentRequest:
            raise
        except (StopIteration, TypeError, ValueError) as error:
            raise CitationDocumentProjectionConflict from error
        except ValidationError as error:
            raise MalformedProviderProjection from error

    def read_transcript_collection(self) -> TranscriptCollectionResponse:
        try:
            registry = self.service.registry.project()
            documents = tuple(
                _transcript_summary(self._owner_transcript(document_id))
                for document_id in registry.successful_document_ids
            )
            return TranscriptCollectionResponse(documents=documents)
        except CitationDocumentRegistryError as error:
            raise TranscriptUnavailable from error
        except (TypeError, ValueError, ValidationError) as error:
            raise MalformedProviderProjection from error

    def read_transcript(self, document_id: str) -> TranscriptDocumentResponse:
        try:
            successful = set(
                self.service.registry.project().successful_document_ids
            )
        except CitationDocumentRegistryError as error:
            raise TranscriptUnavailable from error
        if document_id not in successful:
            raise TranscriptNotFound(document_id)
        try:
            return _transcript_response(self._owner_transcript(document_id))
        except CitationDocumentRegistryError as error:
            raise TranscriptUnavailable from error
        except (TypeError, ValueError, ValidationError) as error:
            raise MalformedProviderProjection from error

    def _owner_transcript(
        self, document_id: str
    ) -> DocumentTranscriptProjection:
        return self.service.registry.transcript(
            document_id=document_id,
            package_root=self.service.package_root,
        )

    def _missing_item(self, item_id: str) -> CitationDocumentProjectionItem:
        matches = tuple(
            item
            for item in self.projection_result.projection.items
            if item.item_id == item_id
        )
        if not matches:
            raise CitationDocumentNotFound(item_id)
        if len(matches) != 1:
            raise CitationDocumentUnavailable
        item = matches[0]
        if (
            item.document_status
            is not OwnerDocumentAvailabilityStatus.NOT_OBSERVED
        ):
            raise CitationDocumentProjectionConflict
        return item

    def _projection_with_receipt(
        self,
        base_item: CitationDocumentProjectionItem,
        receipt: CitationDocumentReceipt,
    ) -> CitationDocumentProjectionResult:
        base = self.projection_result.request
        observation = receipt.observation(
            target_snapshot_id=base_item.target_snapshot_id,
            literal_citekey=base_item.literal_citekey,
        )
        by_id = {
            item.observation_id: item for item in base.document_observations
        }
        by_id[observation.observation_id] = observation
        observations = tuple(
            sorted(
                by_id.values(),
                key=lambda item: (item.literal_citekey, item.observation_id),
            )
        )
        request = CitationDocumentProjectionRequest(
            target_snapshot=base.target_snapshot,
            bibliography_bindings=base.bibliography_bindings,
            identity_projection=base.identity_projection,
            document_observations=observations,
            source_document_link_results=base.source_document_link_results,
        )
        return CitationDocumentProjector().project(request=request)


def _require_owner_contracts() -> None:
    if (
        KSDFT_CITATION_TARGET_SOURCE_COMMIT != _EXPECTED_KSDFT_COMMIT
        or KSDFT_CITATION_TARGET_SOURCE_TREE != _EXPECTED_KSDFT_TREE
        or REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT
        != _EXPECTED_REFERENCES_COMMIT
        or REFERENCES_CITATION_DOCUMENT_SOURCE_TREE != _EXPECTED_REFERENCES_TREE
        or INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT
        != _EXPECTED_INGESTION_COMMIT
        or INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE != _EXPECTED_INGESTION_TREE
        or MAX_CITATION_DOCUMENT_PDF_BYTES != _EXPECTED_MAX_PDF_BYTES
    ):
        raise CitationDocumentUnavailable


def _bounded_owner_id(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} identity must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} identity is invalid") from error
    if (
        not value
        or value != value.strip()
        or len(encoded) > 4_096
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in value
        )
    ):
        raise ValueError(f"{label} identity is invalid")
    return value


def _catalog_response(
    result: CitationDocumentProjectionResult,
) -> CitationDocumentCatalogResponse:
    projection = result.projection
    return CitationDocumentCatalogResponse(
        request_id=result.request.request_id,
        result_id=result.result_id,
        projection=CitationDocumentProjectionResponse(
            contract_id=projection.contract_id,
            target_snapshot_id=projection.target_snapshot_id,
            target_projection_id=projection.target_projection_id,
            bibliography_binding_ids=projection.bibliography_binding_ids,
            identity_projection_id=projection.identity_projection_id,
            document_observation_ids=projection.document_observation_ids,
            source_document_link_ids=projection.source_document_link_ids,
            source_documents=tuple(
                _source_document_response(item)
                for item in projection.source_documents
            ),
            items=tuple(_item_response(item) for item in projection.items),
            source_gaps=tuple(
                _source_gap_response(item) for item in projection.source_gaps
            ),
            limitations=projection.limitations,
            projection_id=projection.projection_id,
        ),
    )


def _item_response(
    item: CitationDocumentProjectionItem,
) -> CitationDocumentItemResponse:
    if type(item) is not CitationDocumentProjectionItem:
        raise TypeError("citation document item type is invalid")
    return CitationDocumentItemResponse(
        item_id=OpaqueId(item.item_id),
        target_snapshot_id=item.target_snapshot_id,
        identity_projection_id=item.identity_projection_id,
        literal_citekey=item.literal_citekey,
        occurrence_ids=item.occurrence_ids,
        bibliography_membership_status=CitationBibliographyMembershipStatus(
            item.bibliography_membership_status.value
        ),
        key_resolution_status=CitationKeyResolutionStatus(
            item.key_resolution_status.value
        ),
        identity_items=tuple(
            CitationIdentityItemResponse(
                item_id=value.item_id,
                requested_identity_id=value.requested_identity_id,
                projection_id=value.projection_id,
                status=CitationIdentityStatus(value.status.value),
                reference_id=value.reference_id,
                canonical_citekey=value.canonical_citekey,
                proposed_citekey=value.proposed_citekey,
                successor_reference_ids=value.successor_reference_ids,
            )
            for value in item.identity_items
        ),
        document_status=CitationDocumentAvailabilityStatus(
            item.document_status.value
        ),
        source_document_ids=item.source_document_ids,
        source_document_link_ids=item.source_document_link_ids,
    )


def _source_document_response(
    descriptor: CitationSourceDocumentDescriptor,
) -> CitationSourceDocumentResponse:
    return CitationSourceDocumentResponse(
        source_document_id=descriptor.source_document_id,
        sha256=descriptor.sha256,
        byte_size=descriptor.byte_size,
        media_type=descriptor.media_type,
        descriptor_id=descriptor.descriptor_id,
    )


def _source_gap_response(
    value: CitationTargetSourceGap,
) -> CitationSourceGapResponse:
    locator = value.locator
    identity = locator.source_content_identity
    return CitationSourceGapResponse(
        source_gap_id=value.source_gap_id,
        source_gap_index=value.source_gap_index,
        locator=CitationSourceLocatorResponse(
            source_path=locator.source_path,
            source_content_identity=CitationContentIdentityResponse(
                algorithm=identity.algorithm,
                digest=identity.digest,
                byte_count=identity.byte_count,
            ),
            include_index=locator.include_index,
            byte_start=locator.byte_start,
            byte_end=locator.byte_end,
            line=locator.line,
            column=locator.column,
        ),
        reason=value.reason,
        placeholder_identifier=value.placeholder_identifier,
    )


def _receipt_response(
    receipt: CitationDocumentReceipt,
) -> CitationDocumentReceiptResponse:
    receipt.validate_identity()
    return CitationDocumentReceiptResponse(
        source_document=_source_document_response(receipt.source_document),
        receipt_id=receipt.receipt_id,
    )


def _receipt_from_request(
    response: CitationDocumentReceiptResponse,
) -> CitationDocumentReceipt:
    source = response.source_document
    descriptor = CitationSourceDocumentDescriptor(
        source_document_id=str(source.source_document_id),
        sha256=source.sha256,
        byte_size=source.byte_size,
        media_type=source.media_type,
    )
    if descriptor.descriptor_id != source.descriptor_id:
        raise InvalidCitationDocumentRequest
    receipt = CitationDocumentReceipt(source_document=descriptor)
    if receipt.receipt_id != response.receipt_id:
        raise InvalidCitationDocumentRequest
    receipt.validate_identity()
    return receipt


def _process_response(
    result: CitationDocumentIngestionResult,
) -> CitationDocumentProcessResponse:
    result.validate_identity()
    link = result.source_document_link
    return CitationDocumentProcessResponse(
        request_id=result.request_id,
        intent_id=result.intent_id,
        link_result_id=result.link_result_id,
        source_document_link=CitationSourceDocumentLinkResponse(
            creating_request_id=link.creating_request_id,
            prior_projection_id=link.prior_projection_id,
            prior_item_id=link.prior_item_id,
            target_snapshot_id=link.target_snapshot_id,
            identity_projection_id=link.identity_projection_id,
            literal_citekey=link.literal_citekey,
            identity_item_id=link.identity_item_id,
            requested_identity_id=link.requested_identity_id,
            source_document=_source_document_response(link.source_document),
            availability_observation_ids=link.availability_observation_ids,
            pre_effect_intent_id=link.pre_effect_intent_id,
            linkage_basis=link.linkage_basis,
            limitations=link.limitations,
            link_id=link.link_id,
        ),
        receipt_id=result.receipt_id,
        source_document_descriptor_id=result.source_document_descriptor_id,
        document_id=OpaqueId(result.document_id),
        status=CitationDocumentTerminalStatus(result.status.value),
        failure_code=(
            None
            if result.failure_code is None
            else CitationDocumentFailureCode(result.failure_code.value)
        ),
        extraction_bundle_id=result.extraction_bundle_id,
        package_id=result.package_id,
        transcript_projection_id=result.transcript_projection_id,
        physical_page_count=result.physical_page_count,
        publication_action=result.publication_action,
        result_id=result.result_id,
    )


def _transcript_response(
    projection: DocumentTranscriptProjection,
) -> TranscriptDocumentResponse:
    if type(projection) is not DocumentTranscriptProjection:
        raise TypeError("owner transcript projection type is invalid")
    if projection.status is not DocumentTranscriptStatus.AUTOMATED_UNREVIEWED:
        raise ValueError("owner transcript status is invalid")
    return TranscriptDocumentResponse(
        document_id=OpaqueId(projection.document_id),
        display_name=projection.display_name,
        status=TranscriptStatus.AUTOMATED_UNREVIEWED,
        physical_page_count=projection.physical_page_count,
        pages=tuple(_transcript_page(page) for page in projection.pages),
    )


def _transcript_summary(
    projection: DocumentTranscriptProjection,
) -> TranscriptDocumentSummaryResponse:
    response = _transcript_response(projection)
    return TranscriptDocumentSummaryResponse.model_validate(
        response.model_dump(exclude={"pages"}),
        strict=True,
    )


def _transcript_page(page: DocumentTranscriptPage) -> TranscriptPageResponse:
    if type(page) is not DocumentTranscriptPage:
        raise TypeError("owner transcript page type is invalid")
    return TranscriptPageResponse(
        page_id=OpaqueId(page.page_id),
        page_index=page.page_index,
        physical_page=page.physical_page,
        printed_page_label=page.printed_page_label,
        text=page.text,
    )
