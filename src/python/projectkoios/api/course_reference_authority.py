from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from projectkoios.api.course_reference_authority_models import (
    ActiveReferenceAuthorityResponse,
    AssetDecisionRequest,
    AssetDisposition,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceQueueItemResponse,
    CourseReferenceQueueResponse,
    CourseReferenceScopeResponse,
    CourseReferenceSelectionResponse,
    CurrentDecisionHeadResponse,
    IdentityDecisionRequest,
    IdentityDisposition,
    IngestionArtifactLinkResponse,
    ObservedCandidateEntryResponse,
    ReferenceAssetResponse,
    ReferenceCandidateResponse,
    ReferenceRecordMatchResponse,
    RenderedCandidateEntryResponse,
)
from projectkoios.courses.reference_resolution import (
    CourseReferenceResolutionScope,
)
from projectkoios.references.course_reference_authority import (
    COURSE_REFERENCE_AUTHORITY_CONTRACT_ID,
    ActiveReferenceAuthority,
    CanonicalAssetCompetitorDisposition,
    CanonicalAssetDecision,
    CanonicalAssetEvidencePlan,
    CourseDisplayCitekeyStatus,
    CourseReferenceAuthorityFailureReason,
    CourseReferenceAuthorityQueue,
    CourseReferenceAuthorityQueueItem,
    CourseReferenceAuthorityService,
    CourseReferenceAuthorityServiceError,
    CourseReferenceResolutionScopeEvidence,
    CourseReferenceRole,
    CourseReferenceSelectionEvidence,
    CourseReferenceSelectionOrigin,
    CurrentReviewDecisionHead,
    ReferenceAssetAuthorityEvidence,
    ReferenceAuthorityDecisionReceipt,
    ReferenceIdentityDecision,
)
from projectkoios.references.course_reference_authority_runtime import (
    CourseReferenceAuthorityRuntimeConfiguration,
    open_course_reference_authority_service,
)
from projectkoios.references.review import (
    ReviewActorKind,
    ReviewActorProvenance,
    ReviewAuthorityScope,
)
from pydantic import ValidationError


class CourseReferenceAuthorityFailure(RuntimeError):
    """Stable API boundary failure carrying no owner-private detail."""

    def __init__(self, code: CourseReferenceFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


class CourseReferenceAuthorityProvider(Protocol):
    def queue(self, course_id: str) -> CourseReferenceQueueResponse: ...

    def decide_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse: ...

    def decide_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse: ...


class UnavailableCourseReferenceAuthorityProvider:
    def queue(self, course_id: str) -> CourseReferenceQueueResponse:
        del course_id
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        )

    def decide_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        del course_id, item_id, request
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        )

    def decide_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        del course_id, item_id, request
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        )


@dataclass(frozen=True, slots=True)
class ReferencesCourseReferenceAuthorityProvider:
    """Compose one Courses scope with the sole References service façade."""

    scope: CourseReferenceResolutionScope
    service: CourseReferenceAuthorityService

    def queue(self, course_id: str) -> CourseReferenceQueueResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            return _queue_response(
                self.service.queue(scope=owner_scope, selections=selections),
                course_scope=self.scope,
            )
        except CourseReferenceAuthorityServiceError as error:
            raise _owner_failure(error) from error
        except (TypeError, ValueError, ValidationError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_MALFORMED
            ) from error
        except (OSError, RuntimeError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            ) from error

    def decide_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            receipt = self.service.put_identity_decision(
                scope=owner_scope,
                selections=selections,
                selection_id=item_id,
                disposition=ReferenceIdentityDecision[request.disposition.name],
                target_state_projection_id=request.target_state_projection_id,
                canonical_citekey=request.canonical_citekey,
                alias_citekeys=request.alias_citekeys,
                selected_record_match_ids=request.selected_record_match_ids,
                expected_current_decision_id=(
                    request.expected_current_decision_id
                ),
                expected_queue_id=request.expected_queue_id,
                expected_item_revision_id=(request.expected_item_revision_id),
                actor=_actor(
                    request,
                    scope=ReviewAuthorityScope.REFERENCE_IDENTITY_CURATOR,
                ),
                rationale=request.rationale,
                decided_at=request.decided_at,
                idempotency_key=request.idempotency_key,
            )
            return _receipt_response(receipt, course_scope=self.scope)
        except CourseReferenceAuthorityServiceError as error:
            raise _owner_failure(error) from error
        except CourseReferenceAuthorityFailure:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_MALFORMED
            ) from error
        except (OSError, RuntimeError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            ) from error

    def decide_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            receipt = self.service.put_asset_decision(
                scope=owner_scope,
                selections=selections,
                selection_id=item_id,
                disposition=CanonicalAssetDecision[request.disposition.name],
                competitor_dispositions=tuple(
                    CanonicalAssetCompetitorDisposition(
                        asset_observation_id=item.asset_observation_id,
                        disposition=CanonicalAssetDecision[
                            item.disposition.name
                        ],
                        rationale=item.rationale,
                    )
                    for item in request.competitors
                ),
                expected_current_decision_id=(
                    request.expected_current_decision_id
                ),
                expected_queue_id=request.expected_queue_id,
                expected_item_revision_id=(request.expected_item_revision_id),
                expected_identity_state_projection_id=(
                    request.expected_identity_state_projection_id
                ),
                expected_plan_id=request.expected_asset_plan_id,
                actor=_actor(
                    request,
                    scope=ReviewAuthorityScope.CANONICAL_ASSET_CURATOR,
                ),
                rationale=request.rationale,
                decided_at=request.decided_at,
                idempotency_key=request.idempotency_key,
            )
            return _receipt_response(receipt, course_scope=self.scope)
        except CourseReferenceAuthorityServiceError as error:
            raise _owner_failure(error) from error
        except CourseReferenceAuthorityFailure:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_MALFORMED
            ) from error
        except (OSError, RuntimeError) as error:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            ) from error

    def _require_course(self, course_id: str) -> None:
        if course_id != self.scope.course_id:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.COURSE_NOT_FOUND
            )

    def _owner_scope(
        self,
    ) -> tuple[
        CourseReferenceResolutionScopeEvidence,
        tuple[CourseReferenceSelectionEvidence, ...],
    ]:
        scope = CourseReferenceResolutionScopeEvidence(
            scope_id=self.scope.scope_id,
            course_id=self.scope.course_id,
            course_title=self.scope.course_title,
            manifest_id=self.scope.manifest_id,
            manifest_sha256=self.scope.manifest_sha256,
            inventory_id=self.scope.inventory_id,
            total=self.scope.total,
            ordered_selection_ids=tuple(
                item.selection_id for item in self.scope.selections
            ),
        )
        selections = tuple(
            CourseReferenceSelectionEvidence(
                scope_id=self.scope.scope_id,
                selection_id=item.selection_id,
                locator_binding_id=item.locator_binding_id,
                course_id=item.course_id,
                manifest_id=item.manifest_id,
                inventory_id=item.inventory_id,
                ordinal=item.ordinal,
                origin=CourseReferenceSelectionOrigin(item.origin.value),
                role=CourseReferenceRole(item.role.value),
                display_citekey=item.display_citekey,
                display_citekey_status=CourseDisplayCitekeyStatus(
                    item.display_citekey_status.value
                ),
                reference_locator=item.reference_locator,
            )
            for item in self.scope.selections
        )
        return scope, selections


def open_references_course_reference_authority_provider(
    *,
    scope: CourseReferenceResolutionScope,
    configuration: CourseReferenceAuthorityRuntimeConfiguration,
) -> ReferencesCourseReferenceAuthorityProvider:
    """Compose typed Courses scope with the References runtime façade."""
    if scope.course_id != configuration.course_id:
        raise ValueError(
            "course reference scope and runtime course identities differ"
        )
    return ReferencesCourseReferenceAuthorityProvider(
        scope=scope,
        service=open_course_reference_authority_service(
            configuration=configuration
        ),
    )


def _actor(
    request: IdentityDecisionRequest | AssetDecisionRequest,
    *,
    scope: ReviewAuthorityScope,
) -> ReviewActorProvenance:
    return ReviewActorProvenance(
        actor_id=request.actor.actor_id,
        actor_kind=ReviewActorKind.PERSON,
        authority_scope=scope,
        authority_domain="projectkoios-references",
        verification_record_id=request.actor.verification_record_id,
        verification_method=request.actor.verification_method,
    )


def _owner_failure(
    error: CourseReferenceAuthorityServiceError,
) -> CourseReferenceAuthorityFailure:
    mapping = {
        CourseReferenceAuthorityFailureReason.COURSE_NOT_FOUND: (
            CourseReferenceFailureCode.COURSE_NOT_FOUND
        ),
        CourseReferenceAuthorityFailureReason.ITEM_NOT_FOUND: (
            CourseReferenceFailureCode.ITEM_NOT_FOUND
        ),
        CourseReferenceAuthorityFailureReason.EVIDENCE_STALE: (
            CourseReferenceFailureCode.EVIDENCE_STALE
        ),
        CourseReferenceAuthorityFailureReason.REVISION_STALE: (
            CourseReferenceFailureCode.REVISION_STALE
        ),
        CourseReferenceAuthorityFailureReason.TARGET_STALE: (
            CourseReferenceFailureCode.TARGET_STALE
        ),
        CourseReferenceAuthorityFailureReason.CONCURRENT_DECISION: (
            CourseReferenceFailureCode.CONCURRENT_DECISION
        ),
        CourseReferenceAuthorityFailureReason.IDEMPOTENCY_CONFLICT: (
            CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT
        ),
        CourseReferenceAuthorityFailureReason.INVALID_DISPOSITION: (
            CourseReferenceFailureCode.INVALID_DISPOSITION
        ),
        CourseReferenceAuthorityFailureReason.OWNER_MALFORMED: (
            CourseReferenceFailureCode.OWNER_MALFORMED
        ),
        CourseReferenceAuthorityFailureReason.OWNER_UNAVAILABLE: (
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        ),
    }
    return CourseReferenceAuthorityFailure(mapping[error.reason])


def _queue_response(
    queue: CourseReferenceAuthorityQueue,
    *,
    course_scope: CourseReferenceResolutionScope,
) -> CourseReferenceQueueResponse:
    items = tuple(
        _item_response(
            queue,
            course_scope=course_scope,
            item=item,
        )
        for item in queue.items
    )
    return CourseReferenceQueueResponse(
        contract_id=COURSE_REFERENCE_AUTHORITY_CONTRACT_ID,
        queue_id=queue.queue_id,
        request_id=queue.request_id,
        scope=CourseReferenceScopeResponse(
            scope_id=queue.scope.scope_id,
            course_id=queue.scope.course_id,
            course_title=queue.scope.course_title,
            manifest_id=queue.scope.manifest_id,
            manifest_sha256=queue.scope.manifest_sha256,
            inventory_id=queue.scope.inventory_id,
            total=queue.scope.total,
            ordered_selection_ids=queue.scope.ordered_selection_ids,
        ),
        items=items,
        active_authorities=tuple(
            _active_authority(item) for item in queue.active_authorities
        ),
        source_export_result_id=queue.source_export_result_id,
        render_result_id=queue.render_result_id,
        review_projection_id=queue.review_projection_id,
        state_projection_ids=queue.state_projection_ids,
    )


def _item_response(
    queue: CourseReferenceAuthorityQueue,
    *,
    course_scope: CourseReferenceResolutionScope,
    item: CourseReferenceAuthorityQueueItem,
) -> CourseReferenceQueueItemResponse:
    candidate = item.candidate
    rendered = item.rendered_entry
    plan_id = None
    if item.active_authority is not None:
        plan_id = CanonicalAssetEvidencePlan(
            queue=queue,
            selection_id=item.selection.selection_id,
            identity_state_projection_id=(
                item.active_authority.state_projection_id
            ),
            assets=item.assets,
        ).plan_id
    return CourseReferenceQueueItemResponse(
        selection=CourseReferenceSelectionResponse(
            scope_id=item.selection.scope_id,
            selection_id=item.selection.selection_id,
            locator_binding_id=item.selection.locator_binding_id,
            course_id=item.selection.course_id,
            manifest_id=item.selection.manifest_id,
            inventory_id=item.selection.inventory_id,
            ordinal=item.selection.ordinal,
            origin=item.selection.origin.value,
            role=item.selection.role.value,
            display_citekey=item.selection.display_citekey,
            display_citekey_status=(
                item.selection.display_citekey_status.value
            ),
            reference_locator=item.selection.reference_locator,
            previous_selection_id=course_scope.previous_selection_id(
                item.selection.selection_id
            ),
            next_selection_id=course_scope.next_selection_id(
                item.selection.selection_id
            ),
        ),
        resolution=item.resolution.value,
        candidate=(
            None
            if candidate is None
            else ReferenceCandidateResponse(
                candidate_id=candidate.candidate_id,
                proposed_citekey=candidate.proposed_citekey,
                entry_type=candidate.entry_type,
                title=candidate.title,
                authors=candidate.authors,
                year=candidate.year,
                doi=candidate.doi,
                isbn=candidate.isbn,
                url=candidate.url,
                eprint=candidate.eprint,
                identity_status=candidate.lifecycle_status,
                citekey_status=candidate.citekey_status,
                source_observation_ids=candidate.source_observation_ids,
            )
        ),
        observations=tuple(
            ObservedCandidateEntryResponse(
                observation_id=value.observation_id,
                source_id=value.source_id,
                asserted_source_revision=value.asserted_source_revision,
                bibliography_sha256=value.bibliography_sha256,
                bibliography_byte_size=value.bibliography_byte_size,
                entry_index=value.entry_index,
                observed_citekey=value.observed_citekey,
                entry_sha256=value.entry_sha256,
                entry_byte_size=value.entry_byte_size,
            )
            for value in item.observations
        ),
        rendered_entry=(
            None
            if rendered is None
            else RenderedCandidateEntryResponse(
                entry_id=rendered.entry_id,
                citekey=rendered.citekey,
                entry_type=rendered.entry_type,
                normalized_fields=rendered.normalized_fields,
                source_observation_ids=rendered.source_observation_ids,
                rendered_sha256=rendered.rendered_sha256,
                rendered_byte_size=rendered.rendered_byte_size,
            )
        ),
        record_matches=tuple(
            ReferenceRecordMatchResponse(
                record_id=value.record_id,
                citekey=value.citekey,
                bibtex_sha256=value.bibtex_sha256,
                bibtex_byte_size=value.bibtex_byte_size,
                authority_status="non-authoritative-discrepancy-observation",
                kind=value.kind.value,
            )
            for value in item.record_matches
        ),
        assets=tuple(_asset_response(value) for value in item.assets),
        current_identity_decisions=tuple(
            _decision_head(value) for value in item.current_identity_decisions
        ),
        current_asset_decision=(
            None
            if item.current_asset_decision is None
            else _decision_head(item.current_asset_decision)
        ),
        active_authority=(
            None
            if item.active_authority is None
            else _active_authority(item.active_authority)
        ),
        allowed_identity_actions=tuple(
            IdentityDisposition[value.name]
            for value in item.allowed_identity_actions
        ),
        allowed_asset_actions=tuple(
            AssetDisposition[value.name] for value in item.allowed_asset_actions
        ),
        asset_plan_id=plan_id,
        item_revision_id=item.item_revision_id,
    )


def _asset_response(
    asset: ReferenceAssetAuthorityEvidence,
) -> ReferenceAssetResponse:
    return ReferenceAssetResponse(
        candidate_id=asset.candidate_id,
        asset_observation_id=asset.asset_observation_id,
        sha256=asset.sha256,
        byte_size=asset.byte_size,
        rights_status=asset.rights_status,
        asset_status=asset.asset_status,
        runtime_availability=asset.runtime_availability.value,
        runtime_evidence_id=asset.runtime_evidence_id,
        document_binding_ids=asset.document_binding_ids,
        ingestion_evidence_ids=asset.ingestion_evidence_ids,
        ingestion_artifact_links=tuple(
            IngestionArtifactLinkResponse(
                link_id=link.link_id,
                asset_observation_id=link.asset_observation_id,
                source_id=link.source_id,
                document_id=link.document_id,
                artifact_verification_result_id=(
                    link.artifact_verification_result_id
                ),
            )
            for link in asset.ingestion_artifact_links
        ),
    )


def _decision_head(
    head: CurrentReviewDecisionHead,
) -> CurrentDecisionHeadResponse:
    return CurrentDecisionHeadResponse(
        decision_id=head.decision_id,
        subject_id=head.subject_id,
        context_id=head.context_id,
        dimension=head.dimension.value,
        decision=head.decision,
        actor_id=head.actor_id,
        authority_scope=head.authority_scope,
        actor_verification_record_id=head.actor_verification_record_id,
        decided_at=head.decided_at,
    )


def _active_authority(
    authority: ActiveReferenceAuthority,
) -> ActiveReferenceAuthorityResponse:
    return ActiveReferenceAuthorityResponse(
        candidate_id=authority.candidate_id,
        state_projection_id=authority.state_projection_id,
        bibliographic_work_id=authority.bibliographic_work_id,
        active_citekey=authority.active_citekey,
        alias_citekeys=authority.alias_citekeys,
        identity_decision_id=authority.identity_decision_id,
        source_asset_id=authority.source_asset_id,
        canonical_asset_decision_id=(authority.canonical_asset_decision_id),
        authority_binding_id=authority.authority_binding_id,
    )


def _receipt_response(
    receipt: ReferenceAuthorityDecisionReceipt,
    *,
    course_scope: CourseReferenceResolutionScope,
) -> CourseReferenceDecisionReceiptResponse:
    queue_response = _queue_response(
        receipt.refreshed_queue,
        course_scope=course_scope,
    )
    refreshed_item = next(
        item
        for item in queue_response.items
        if item.selection.selection_id
        == receipt.refreshed_item.selection.selection_id
    )
    decision = receipt.decision_result.decision
    return CourseReferenceDecisionReceiptResponse(
        receipt_id=receipt.receipt_id,
        result_id=receipt.decision_result.result_id,
        request_id=receipt.decision_result.request_id,
        preview_id=receipt.preview_id,
        decision_id=decision.decision_id,
        dimension=decision.dimension.value,
        disposition=decision.decision.upper().replace("-", "_"),
        state_projection_id=receipt.current_state_projection_id,
        current_decision_id=receipt.current_decision_id,
        refreshed_queue_id=receipt.refreshed_queue_id,
        refreshed_item_revision_id=receipt.refreshed_item_revision_id,
        refreshed_item=refreshed_item,
    )
