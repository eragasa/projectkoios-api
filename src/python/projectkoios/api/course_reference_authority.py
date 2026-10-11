from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from projectkoios.api.config import CourseReferenceAuthorityActorConfiguration
from projectkoios.api.course_reference_authority_models import (
    ActiveReferenceAuthorityResponse,
    AssetCompetitorDecisionRequest,
    AssetCompetitorDecisionResponse,
    AssetDecisionPreviewRequest,
    AssetDecisionPreviewResponse,
    AssetDecisionRequest,
    AssetDisposition,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceQueueItemResponse,
    CourseReferenceQueueResponse,
    CourseReferenceScopeResponse,
    CourseReferenceSelectionResponse,
    CurrentDecisionHeadResponse,
    IdentityDecisionPreviewRequest,
    IdentityDecisionPreviewResponse,
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
from projectkoios.references.courses.authority import (
    COURSE_REFERENCE_AUTHORITY_CONTRACT_ID,
    ActiveReferenceAuthority,
    CanonicalAssetCompetitorDisposition,
    CanonicalAssetDecisionPreviewActionizer,
    CanonicalAssetDecisionPreviewRequest,
    CanonicalAssetDecisionPreviewResult,
    CourseDisplayCitekeyStatus,
    CourseReferenceAuthorityFailureReason,
    CourseReferenceAuthorityQueue,
    CourseReferenceAuthorityQueueItem,
    CourseReferenceAuthorityQueueLoadActionizer,
    CourseReferenceAuthorityQueueLoadRequest,
    CourseReferenceAuthorityServiceError,
    CourseReferenceResolutionScopeEvidence,
    CourseReferenceRole,
    CourseReferenceSelectionEvidence,
    CourseReferenceSelectionOrigin,
    CurrentReviewDecisionHead,
    PutCanonicalAssetDecisionActionizer,
    PutCanonicalAssetDecisionRequest,
    PutReferenceIdentityDecisionActionizer,
    PutReferenceIdentityDecisionRequest,
    ReferenceAssetAuthorityEvidence,
    ReferenceAuthorityDecisionPutResult,
    ReferenceIdentityDecisionPreviewActionizer,
    ReferenceIdentityDecisionPreviewRequest,
    ReferenceIdentityDecisionPreviewResult,
)
from projectkoios.references.courses.runtime import (
    CourseReferenceAuthorityRuntimeConfiguration,
    FilesystemCourseReferenceAuthorityRuntime,
)
from projectkoios.references.review import (
    CanonicalAssetDecision,
    ReferenceIdentityDecision,
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


class CourseReferenceAuthorityRuntime(Protocol):
    queue: CourseReferenceAuthorityQueueLoadActionizer
    identity_preview: ReferenceIdentityDecisionPreviewActionizer
    asset_preview: CanonicalAssetDecisionPreviewActionizer
    identity_put: PutReferenceIdentityDecisionActionizer
    asset_put: PutCanonicalAssetDecisionActionizer


class CourseReferenceAuthorityProvider(Protocol):
    def queue(self, course_id: str) -> CourseReferenceQueueResponse: ...

    def preview_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionPreviewRequest,
    ) -> IdentityDecisionPreviewResponse: ...

    def preview_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionPreviewRequest,
    ) -> AssetDecisionPreviewResponse: ...

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

    def preview_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionPreviewRequest,
    ) -> IdentityDecisionPreviewResponse:
        del course_id, item_id, request
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        )

    def preview_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionPreviewRequest,
    ) -> AssetDecisionPreviewResponse:
        del course_id, item_id, request
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
    runtime: CourseReferenceAuthorityRuntime
    actor: CourseReferenceAuthorityActorConfiguration

    def queue(self, course_id: str) -> CourseReferenceQueueResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            return _queue_response(
                self.runtime.queue.action(
                    request=CourseReferenceAuthorityQueueLoadRequest(
                        scope=owner_scope,
                        selections=selections,
                    )
                ),
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

    def preview_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionPreviewRequest,
    ) -> IdentityDecisionPreviewResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            preview = self.runtime.identity_preview.action(
                request=_identity_preview_request(
                    scope=owner_scope,
                    selections=selections,
                    selection_id=item_id,
                    request=request,
                )
            )
            _require_expected_projection(
                queue_id=preview.queue_id,
                item_revision_id=preview.item_revision_id,
                expected_queue_id=request.expected_queue_id,
                expected_item_revision_id=request.expected_item_revision_id,
            )
            return _identity_preview_response(preview)
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

    def preview_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionPreviewRequest,
    ) -> AssetDecisionPreviewResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            preview = self.runtime.asset_preview.action(
                request=_asset_preview_request(
                    scope=owner_scope,
                    selections=selections,
                    selection_id=item_id,
                    request=request,
                )
            )
            _require_expected_projection(
                queue_id=preview.queue_id,
                item_revision_id=preview.item_revision_id,
                expected_queue_id=request.expected_queue_id,
                expected_item_revision_id=request.expected_item_revision_id,
            )
            if (
                preview.identity_state_projection_id
                != request.expected_identity_state_projection_id
            ):
                raise CourseReferenceAuthorityFailure(
                    CourseReferenceFailureCode.REVISION_STALE
                )
            return _asset_preview_response(preview)
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

    def decide_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        self._require_course(course_id)
        try:
            owner_scope, selections = self._owner_scope()
            result = self.runtime.identity_put.action(
                request=PutReferenceIdentityDecisionRequest(
                    preview_request=_identity_preview_request(
                        scope=owner_scope,
                        selections=selections,
                        selection_id=item_id,
                        request=request,
                    ),
                    expected_preview_id=request.expected_preview_id,
                    expected_preview_result_id=(
                        request.expected_preview_result_id
                    ),
                    expected_queue_id=request.expected_queue_id,
                    expected_item_revision_id=(
                        request.expected_item_revision_id
                    ),
                    actor=_actor(
                        self.actor,
                        scope=(ReviewAuthorityScope.REFERENCE_IDENTITY_CURATOR),
                    ),
                    rationale=request.rationale,
                    decided_at=request.decided_at,
                    idempotency_key=request.idempotency_key,
                )
            )
            return _put_response(
                result,
                dimension="reference-identity",
                disposition=request.disposition.value,
            )
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
            result = self.runtime.asset_put.action(
                request=PutCanonicalAssetDecisionRequest(
                    preview_request=_asset_preview_request(
                        scope=owner_scope,
                        selections=selections,
                        selection_id=item_id,
                        request=request,
                    ),
                    expected_preview_id=request.expected_preview_id,
                    expected_preview_result_id=(
                        request.expected_preview_result_id
                    ),
                    expected_queue_id=request.expected_queue_id,
                    expected_item_revision_id=(
                        request.expected_item_revision_id
                    ),
                    expected_identity_state_projection_id=(
                        request.expected_identity_state_projection_id
                    ),
                    expected_plan_id=request.expected_asset_plan_id,
                    actor=_actor(
                        self.actor,
                        scope=ReviewAuthorityScope.CANONICAL_ASSET_CURATOR,
                    ),
                    rationale=request.rationale,
                    decided_at=request.decided_at,
                    idempotency_key=request.idempotency_key,
                )
            )
            return _put_response(
                result,
                dimension="canonical-asset",
                disposition=request.disposition.value,
            )
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
    actor: CourseReferenceAuthorityActorConfiguration,
) -> ReferencesCourseReferenceAuthorityProvider:
    """Compose typed Courses scope with the References runtime façade."""
    if scope.course_id != configuration.course_id:
        raise ValueError(
            "course reference scope and runtime course identities differ"
        )
    return ReferencesCourseReferenceAuthorityProvider(
        scope=scope,
        runtime=FilesystemCourseReferenceAuthorityRuntime(
            configuration=configuration
        ),
        actor=actor,
    )


def _actor(
    actor: CourseReferenceAuthorityActorConfiguration,
    *,
    scope: ReviewAuthorityScope,
) -> ReviewActorProvenance:
    return ReviewActorProvenance(
        actor_id=actor.actor_id,
        actor_kind=ReviewActorKind.PERSON,
        authority_scope=scope,
        authority_domain="projectkoios-references",
        verification_record_id=actor.verification_record_id,
        verification_method=actor.verification_method,
    )


def _competitor_dispositions(
    competitors: tuple[AssetCompetitorDecisionRequest, ...],
) -> tuple[CanonicalAssetCompetitorDisposition, ...]:
    return tuple(
        CanonicalAssetCompetitorDisposition(
            asset_observation_id=item.asset_observation_id,
            disposition=CanonicalAssetDecision[item.disposition.name],
            rationale=item.rationale,
        )
        for item in competitors
    )


def _require_expected_projection(
    *,
    queue_id: str,
    item_revision_id: str,
    expected_queue_id: str,
    expected_item_revision_id: str,
) -> None:
    if queue_id != expected_queue_id:
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.EVIDENCE_STALE
        )
    if item_revision_id != expected_item_revision_id:
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.REVISION_STALE
        )


def _identity_preview_request(
    *,
    scope: CourseReferenceResolutionScopeEvidence,
    selections: tuple[CourseReferenceSelectionEvidence, ...],
    selection_id: str,
    request: IdentityDecisionPreviewRequest | IdentityDecisionRequest,
) -> ReferenceIdentityDecisionPreviewRequest:
    return ReferenceIdentityDecisionPreviewRequest(
        scope=scope,
        selections=selections,
        selection_id=selection_id,
        disposition=ReferenceIdentityDecision[request.disposition.name],
        target_state_projection_id=request.target_state_projection_id,
        canonical_citekey=request.canonical_citekey,
        alias_citekeys=request.alias_citekeys,
        selected_record_match_ids=request.selected_record_match_ids,
        expected_current_decision_id=request.expected_current_decision_id,
    )


def _asset_preview_request(
    *,
    scope: CourseReferenceResolutionScopeEvidence,
    selections: tuple[CourseReferenceSelectionEvidence, ...],
    selection_id: str,
    request: AssetDecisionPreviewRequest | AssetDecisionRequest,
) -> CanonicalAssetDecisionPreviewRequest:
    return CanonicalAssetDecisionPreviewRequest(
        scope=scope,
        selections=selections,
        selection_id=selection_id,
        disposition=CanonicalAssetDecision[request.disposition.name],
        competitor_dispositions=_competitor_dispositions(request.competitors),
        expected_current_decision_id=request.expected_current_decision_id,
    )


def _identity_preview_response(
    preview: ReferenceIdentityDecisionPreviewResult,
) -> IdentityDecisionPreviewResponse:
    return IdentityDecisionPreviewResponse(
        request_id=preview.request_id,
        result_id=preview.result_id,
        preview_id=preview.preview_id,
        selection_id=preview.selection_id,
        disposition=IdentityDisposition[preview.disposition.name],
        target_state_projection_id=preview.target_state_projection_id,
        canonical_citekey=preview.canonical_citekey,
        alias_citekeys=preview.alias_citekeys,
        selected_record_match_ids=preview.selected_record_match_ids,
        expected_current_decision_id=preview.expected_current_decision_id,
        queue_id=preview.queue_id,
        item_revision_id=preview.item_revision_id,
    )


def _asset_preview_response(
    preview: CanonicalAssetDecisionPreviewResult,
) -> AssetDecisionPreviewResponse:
    return AssetDecisionPreviewResponse(
        request_id=preview.request_id,
        result_id=preview.result_id,
        preview_id=preview.preview_id,
        plan_id=preview.plan_id,
        selection_id=preview.selection_id,
        disposition=AssetDisposition[preview.disposition.name],
        identity_state_projection_id=(preview.identity_state_projection_id),
        competitors=tuple(
            AssetCompetitorDecisionResponse(
                asset_observation_id=competitor.asset_observation_id,
                disposition=AssetDisposition[competitor.disposition.name],
                rationale=competitor.rationale,
            )
            for competitor in preview.competitor_dispositions
        ),
        selected_asset_observation_id=preview.selected_asset_observation_id,
        expected_current_decision_id=preview.expected_current_decision_id,
        queue_id=preview.queue_id,
        item_revision_id=preview.item_revision_id,
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
    *,
    course_scope: CourseReferenceResolutionScope,
    item: CourseReferenceAuthorityQueueItem,
) -> CourseReferenceQueueItemResponse:
    candidate = item.candidate
    rendered = item.rendered_entry
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


def _put_response(
    result: ReferenceAuthorityDecisionPutResult,
    *,
    dimension: Literal["reference-identity", "canonical-asset"],
    disposition: str,
) -> CourseReferenceDecisionReceiptResponse:
    return CourseReferenceDecisionReceiptResponse(
        receipt_id=result.receipt_id,
        result_id=result.result_id,
        put_request_id=result.put_request_id,
        decision_append_request_id=result.decision_append_request_id,
        preview_id=result.preview_id,
        decision_id=result.decision_id,
        dimension=dimension,
        disposition=disposition,
        state_projection_id=result.state_projection_id,
        current_decision_id=result.current_decision_id,
        current_state_projection_id=result.current_state_projection_id,
        refreshed_queue_id=result.refreshed_queue_id,
        refreshed_item_revision_id=result.refreshed_item_revision_id,
    )
