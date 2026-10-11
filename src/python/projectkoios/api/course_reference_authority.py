from __future__ import annotations

from dataclasses import dataclass

from projectkoios.api.config import CourseReferenceAuthorityActorConfiguration
from projectkoios.api.course_reference_authority_models import (
    AssetCompetitorDecisionRequest,
    AssetDecisionPreviewRequest,
    AssetDecisionPreviewResponse,
    AssetDecisionRequest,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceQueueResponse,
    IdentityDecisionPreviewRequest,
    IdentityDecisionPreviewResponse,
    IdentityDecisionRequest,
)
from projectkoios.base import (
    DataObjectActionizer,
    DataObjectActionRequest,
    DataObjectActionResult,
    DataObjectModel,
)
from projectkoios.courses.reference_resolution import (
    CourseReferenceResolutionScope,
)
from projectkoios.references.courses.authority.scope import (
    CourseDisplayCitekeyStatus,
    CourseReferenceResolutionScopeEvidence,
    CourseReferenceRole,
    CourseReferenceSelectionEvidence,
    CourseReferenceSelectionOrigin,
)
from projectkoios.references.courses.authority.service import (
    CourseReferenceAuthorityFailureReason,
    CourseReferenceAuthorityServiceError,
)
from projectkoios.references.courses.runtime.configuration import (
    CourseReferenceAuthorityRuntimeConfiguration,
)
from projectkoios.references.courses.runtime.facade import (
    FilesystemCourseReferenceAuthorityRuntimeCreateActionizer,
    FilesystemCourseReferenceAuthorityRuntimeCreateRequest,
)
from projectkoios.references.courses.transport.asset import (
    CanonicalAssetPreviewTransportActionizer,
    CanonicalAssetPreviewTransportRequest,
    CanonicalAssetPutTransportActionizer,
    CanonicalAssetPutTransportRequest,
)
from projectkoios.references.courses.transport.identity import (
    ReferenceIdentityPreviewTransportActionizer,
    ReferenceIdentityPreviewTransportRequest,
    ReferenceIdentityPutTransportActionizer,
    ReferenceIdentityPutTransportRequest,
)
from projectkoios.references.courses.transport.queue import (
    CourseReferenceQueueTransportActionizer,
    CourseReferenceQueueTransportRequest,
)
from pydantic import ValidationError


class CourseReferenceAuthorityFailure(RuntimeError):
    """Carry one stable API boundary failure with no owner-private detail."""

    def __init__(self, code: CourseReferenceFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True, kw_only=True)
class CourseReferenceAuthorityScopeBinding(DataObjectModel):
    """Bind one validated Courses result to References-owned scope evidence."""

    course_scope: CourseReferenceResolutionScope
    owner_scope: CourseReferenceResolutionScopeEvidence
    owner_selections: tuple[CourseReferenceSelectionEvidence, ...]

    def __post_init__(self) -> None:
        if type(self.course_scope) is not CourseReferenceResolutionScope:
            raise TypeError("course_scope has an invalid type")
        if type(self.owner_scope) is not CourseReferenceResolutionScopeEvidence:
            raise TypeError("owner_scope has an invalid type")
        if not isinstance(self.owner_selections, tuple) or any(
            type(item) is not CourseReferenceSelectionEvidence
            for item in self.owner_selections
        ):
            raise TypeError("owner_selections must be an exact typed tuple")
        if self.course_scope.course_id != self.owner_scope.course_id:
            raise ValueError("course scope bindings differ")


@dataclass(frozen=True, slots=True, kw_only=True)
class CourseReferenceQueueHttpRequest(DataObjectActionRequest):
    """Request the current course-scoped authority queue."""

    course_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CourseReferenceQueueHttpResult(DataObjectActionResult):
    """Return one validated owner-authored queue JSON body."""

    body_json: str


class CourseReferenceQueueHttpActionizer(
    DataObjectActionizer[
        CourseReferenceQueueHttpRequest,
        CourseReferenceQueueHttpResult,
    ]
):
    """Execute only the course-reference queue HTTP boundary action."""

    __slots__ = ("_binding", "_owner")

    def __init__(
        self,
        *,
        binding: CourseReferenceAuthorityScopeBinding | None,
        owner: CourseReferenceQueueTransportActionizer | None,
    ) -> None:
        self._binding = binding
        self._owner = owner

    def action(
        self,
        *,
        request: CourseReferenceQueueHttpRequest,
    ) -> CourseReferenceQueueHttpResult:
        """Return the current complete queue."""
        if type(request) is not CourseReferenceQueueHttpRequest:
            raise TypeError("request has an invalid type")
        binding = _require_binding(request.course_id, self._binding)
        owner = self._owner
        if owner is None:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            )
        try:
            result = owner.action(
                request=CourseReferenceQueueTransportRequest(
                    scope=binding.owner_scope,
                    selections=binding.owner_selections,
                )
            )
            CourseReferenceQueueResponse.model_validate_json(result.body_json)
            return CourseReferenceQueueHttpResult(body_json=result.body_json)
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIdentityPreviewHttpRequest(DataObjectActionRequest):
    """Request one owner-generated identity consequence preview."""

    course_id: str
    item_id: str
    body: IdentityDecisionPreviewRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIdentityPreviewHttpResult(DataObjectActionResult):
    """Return one validated owner-authored identity-preview JSON body."""

    body_json: str


class ReferenceIdentityPreviewHttpActionizer(
    DataObjectActionizer[
        ReferenceIdentityPreviewHttpRequest,
        ReferenceIdentityPreviewHttpResult,
    ]
):
    """Execute only the identity-preview HTTP boundary action."""

    __slots__ = ("_binding", "_owner")

    def __init__(
        self,
        *,
        binding: CourseReferenceAuthorityScopeBinding | None,
        owner: ReferenceIdentityPreviewTransportActionizer | None,
    ) -> None:
        self._binding = binding
        self._owner = owner

    def action(
        self,
        *,
        request: ReferenceIdentityPreviewHttpRequest,
    ) -> ReferenceIdentityPreviewHttpResult:
        """Return one current owner-generated identity preview."""
        if type(request) is not ReferenceIdentityPreviewHttpRequest:
            raise TypeError("request has an invalid type")
        binding = _require_binding(request.course_id, self._binding)
        owner = self._owner
        if owner is None:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            )
        body = request.body
        try:
            result = owner.action(
                request=ReferenceIdentityPreviewTransportRequest(
                    scope=binding.owner_scope,
                    selections=binding.owner_selections,
                    selection_id=request.item_id,
                    expected_queue_id=body.expected_queue_id,
                    expected_item_revision_id=body.expected_item_revision_id,
                    disposition=body.disposition.value,
                    target_state_projection_id=(
                        body.target_state_projection_id
                    ),
                    canonical_citekey=body.canonical_citekey,
                    alias_citekeys=body.alias_citekeys,
                    selected_record_match_ids=(body.selected_record_match_ids),
                    expected_current_decision_id=(
                        body.expected_current_decision_id
                    ),
                )
            )
            IdentityDecisionPreviewResponse.model_validate_json(
                result.body_json
            )
            return ReferenceIdentityPreviewHttpResult(
                body_json=result.body_json
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


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalAssetPreviewHttpRequest(DataObjectActionRequest):
    """Request one owner-generated canonical-asset consequence preview."""

    course_id: str
    item_id: str
    body: AssetDecisionPreviewRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalAssetPreviewHttpResult(DataObjectActionResult):
    """Return one validated owner-authored asset-preview JSON body."""

    body_json: str


class CanonicalAssetPreviewHttpActionizer(
    DataObjectActionizer[
        CanonicalAssetPreviewHttpRequest,
        CanonicalAssetPreviewHttpResult,
    ]
):
    """Execute only the canonical-asset-preview HTTP boundary action."""

    __slots__ = ("_binding", "_owner")

    def __init__(
        self,
        *,
        binding: CourseReferenceAuthorityScopeBinding | None,
        owner: CanonicalAssetPreviewTransportActionizer | None,
    ) -> None:
        self._binding = binding
        self._owner = owner

    def action(
        self,
        *,
        request: CanonicalAssetPreviewHttpRequest,
    ) -> CanonicalAssetPreviewHttpResult:
        """Return one current owner-generated asset preview."""
        if type(request) is not CanonicalAssetPreviewHttpRequest:
            raise TypeError("request has an invalid type")
        binding = _require_binding(request.course_id, self._binding)
        owner = self._owner
        if owner is None:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            )
        body = request.body
        try:
            result = owner.action(
                request=CanonicalAssetPreviewTransportRequest(
                    scope=binding.owner_scope,
                    selections=binding.owner_selections,
                    selection_id=request.item_id,
                    expected_queue_id=body.expected_queue_id,
                    expected_item_revision_id=body.expected_item_revision_id,
                    expected_identity_state_projection_id=(
                        body.expected_identity_state_projection_id
                    ),
                    disposition=body.disposition.value,
                    competitors=_competitors(body.competitors),
                    expected_current_decision_id=(
                        body.expected_current_decision_id
                    ),
                )
            )
            AssetDecisionPreviewResponse.model_validate_json(result.body_json)
            return CanonicalAssetPreviewHttpResult(body_json=result.body_json)
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIdentityPutHttpRequest(DataObjectActionRequest):
    """Request one preview-bound idempotent identity decision PUT."""

    course_id: str
    item_id: str
    body: IdentityDecisionRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceIdentityPutHttpResult(DataObjectActionResult):
    """Return one validated owner-authored identity receipt JSON body."""

    body_json: str


class ReferenceIdentityPutHttpActionizer(
    DataObjectActionizer[
        ReferenceIdentityPutHttpRequest,
        ReferenceIdentityPutHttpResult,
    ]
):
    """Execute only the identity-decision PUT HTTP boundary action."""

    __slots__ = ("_actor", "_binding", "_owner")

    def __init__(
        self,
        *,
        binding: CourseReferenceAuthorityScopeBinding | None,
        owner: ReferenceIdentityPutTransportActionizer | None,
        actor: CourseReferenceAuthorityActorConfiguration | None,
    ) -> None:
        self._binding = binding
        self._owner = owner
        self._actor = actor

    def action(
        self,
        *,
        request: ReferenceIdentityPutHttpRequest,
    ) -> ReferenceIdentityPutHttpResult:
        """Return one verified identity-decision receipt."""
        if type(request) is not ReferenceIdentityPutHttpRequest:
            raise TypeError("request has an invalid type")
        binding = _require_binding(request.course_id, self._binding)
        owner = self._owner
        actor = self._actor
        if owner is None or actor is None:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            )
        body = request.body
        try:
            result = owner.action(
                request=ReferenceIdentityPutTransportRequest(
                    scope=binding.owner_scope,
                    selections=binding.owner_selections,
                    selection_id=request.item_id,
                    idempotency_key=body.idempotency_key,
                    expected_queue_id=body.expected_queue_id,
                    expected_item_revision_id=body.expected_item_revision_id,
                    expected_preview_id=body.expected_preview_id,
                    expected_preview_result_id=(
                        body.expected_preview_result_id
                    ),
                    expected_current_decision_id=(
                        body.expected_current_decision_id
                    ),
                    disposition=body.disposition.value,
                    target_state_projection_id=(
                        body.target_state_projection_id
                    ),
                    canonical_citekey=body.canonical_citekey,
                    alias_citekeys=body.alias_citekeys,
                    selected_record_match_ids=(body.selected_record_match_ids),
                    rationale=body.rationale,
                    decided_at=body.decided_at,
                    actor_id=actor.actor_id,
                    actor_verification_record_id=(actor.verification_record_id),
                    actor_verification_method=actor.verification_method,
                )
            )
            CourseReferenceDecisionReceiptResponse.model_validate_json(
                result.body_json
            )
            return ReferenceIdentityPutHttpResult(body_json=result.body_json)
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


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalAssetPutHttpRequest(DataObjectActionRequest):
    """Request one preview-bound idempotent canonical-asset decision PUT."""

    course_id: str
    item_id: str
    body: AssetDecisionRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalAssetPutHttpResult(DataObjectActionResult):
    """Return one validated owner-authored asset receipt JSON body."""

    body_json: str


class CanonicalAssetPutHttpActionizer(
    DataObjectActionizer[
        CanonicalAssetPutHttpRequest,
        CanonicalAssetPutHttpResult,
    ]
):
    """Execute only the canonical-asset PUT HTTP boundary action."""

    __slots__ = ("_actor", "_binding", "_owner")

    def __init__(
        self,
        *,
        binding: CourseReferenceAuthorityScopeBinding | None,
        owner: CanonicalAssetPutTransportActionizer | None,
        actor: CourseReferenceAuthorityActorConfiguration | None,
    ) -> None:
        self._binding = binding
        self._owner = owner
        self._actor = actor

    def action(
        self,
        *,
        request: CanonicalAssetPutHttpRequest,
    ) -> CanonicalAssetPutHttpResult:
        """Return one verified canonical-asset receipt."""
        if type(request) is not CanonicalAssetPutHttpRequest:
            raise TypeError("request has an invalid type")
        binding = _require_binding(request.course_id, self._binding)
        owner = self._owner
        actor = self._actor
        if owner is None or actor is None:
            raise CourseReferenceAuthorityFailure(
                CourseReferenceFailureCode.OWNER_UNAVAILABLE
            )
        body = request.body
        try:
            result = owner.action(
                request=CanonicalAssetPutTransportRequest(
                    scope=binding.owner_scope,
                    selections=binding.owner_selections,
                    selection_id=request.item_id,
                    idempotency_key=body.idempotency_key,
                    expected_queue_id=body.expected_queue_id,
                    expected_item_revision_id=body.expected_item_revision_id,
                    expected_preview_id=body.expected_preview_id,
                    expected_preview_result_id=(
                        body.expected_preview_result_id
                    ),
                    expected_identity_state_projection_id=(
                        body.expected_identity_state_projection_id
                    ),
                    expected_asset_plan_id=body.expected_asset_plan_id,
                    expected_current_decision_id=(
                        body.expected_current_decision_id
                    ),
                    disposition=body.disposition.value,
                    competitors=_competitors(body.competitors),
                    rationale=body.rationale,
                    decided_at=body.decided_at,
                    actor_id=actor.actor_id,
                    actor_verification_record_id=(actor.verification_record_id),
                    actor_verification_method=actor.verification_method,
                )
            )
            CourseReferenceDecisionReceiptResponse.model_validate_json(
                result.body_json
            )
            return CanonicalAssetPutHttpResult(body_json=result.body_json)
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


@dataclass(frozen=True, slots=True, kw_only=True)
class CourseReferenceAuthorityHttpActionsCreateRequest(DataObjectActionRequest):
    """Request configured or explicitly unavailable HTTP action capabilities."""

    scope: CourseReferenceResolutionScope | None
    configuration: CourseReferenceAuthorityRuntimeConfiguration | None
    actor: CourseReferenceAuthorityActorConfiguration | None

    def __post_init__(self) -> None:
        configured = (
            self.scope is not None,
            self.configuration is not None,
            self.actor is not None,
        )
        if any(configured) and not all(configured):
            raise ValueError(
                "course reference authority composition must be complete"
            )
        if self.scope is not None and type(self.scope) is not (
            CourseReferenceResolutionScope
        ):
            raise TypeError("scope has an invalid type")
        if self.configuration is not None and type(self.configuration) is not (
            CourseReferenceAuthorityRuntimeConfiguration
        ):
            raise TypeError("configuration has an invalid type")
        if self.actor is not None and type(self.actor) is not (
            CourseReferenceAuthorityActorConfiguration
        ):
            raise TypeError("actor has an invalid type")
        if (
            self.scope is not None
            and self.configuration is not None
            and self.scope.course_id != self.configuration.course_id
        ):
            raise ValueError(
                "course reference scope and runtime course identities differ"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CourseReferenceAuthorityHttpActionsCreateResult(DataObjectActionResult):
    """Expose the exact five course-reference HTTP action capabilities."""

    queue: CourseReferenceQueueHttpActionizer
    identity_preview: ReferenceIdentityPreviewHttpActionizer
    asset_preview: CanonicalAssetPreviewHttpActionizer
    identity_put: ReferenceIdentityPutHttpActionizer
    asset_put: CanonicalAssetPutHttpActionizer


class CourseReferenceAuthorityHttpActionsCreateActionizer(
    DataObjectActionizer[
        CourseReferenceAuthorityHttpActionsCreateRequest,
        CourseReferenceAuthorityHttpActionsCreateResult,
    ]
):
    """Compose five explicit HTTP actions from trusted owner capabilities."""

    __slots__ = ()

    def action(
        self,
        *,
        request: CourseReferenceAuthorityHttpActionsCreateRequest,
    ) -> CourseReferenceAuthorityHttpActionsCreateResult:
        """Return configured actions or explicit unavailable actions."""
        if (
            type(request)
            is not CourseReferenceAuthorityHttpActionsCreateRequest
        ):
            raise TypeError("request has an invalid type")
        if request.scope is None:
            return _http_actions(
                binding=None,
                actor=None,
                queue=None,
                identity_preview=None,
                asset_preview=None,
                identity_put=None,
                asset_put=None,
            )
        configuration = request.configuration
        actor = request.actor
        if configuration is None or actor is None:
            raise ValueError("configured composition is incomplete")
        runtime = (
            FilesystemCourseReferenceAuthorityRuntimeCreateActionizer().action(
                request=FilesystemCourseReferenceAuthorityRuntimeCreateRequest(
                    configuration=configuration
                )
            )
        )
        return _http_actions(
            binding=_scope_binding(request.scope),
            actor=actor,
            queue=runtime.queue,
            identity_preview=runtime.identity_preview,
            asset_preview=runtime.asset_preview,
            identity_put=runtime.identity_put,
            asset_put=runtime.asset_put,
        )


def _http_actions(
    *,
    binding: CourseReferenceAuthorityScopeBinding | None,
    actor: CourseReferenceAuthorityActorConfiguration | None,
    queue: CourseReferenceQueueTransportActionizer | None,
    identity_preview: ReferenceIdentityPreviewTransportActionizer | None,
    asset_preview: CanonicalAssetPreviewTransportActionizer | None,
    identity_put: ReferenceIdentityPutTransportActionizer | None,
    asset_put: CanonicalAssetPutTransportActionizer | None,
) -> CourseReferenceAuthorityHttpActionsCreateResult:
    return CourseReferenceAuthorityHttpActionsCreateResult(
        queue=CourseReferenceQueueHttpActionizer(
            binding=binding,
            owner=queue,
        ),
        identity_preview=ReferenceIdentityPreviewHttpActionizer(
            binding=binding,
            owner=identity_preview,
        ),
        asset_preview=CanonicalAssetPreviewHttpActionizer(
            binding=binding,
            owner=asset_preview,
        ),
        identity_put=ReferenceIdentityPutHttpActionizer(
            binding=binding,
            owner=identity_put,
            actor=actor,
        ),
        asset_put=CanonicalAssetPutHttpActionizer(
            binding=binding,
            owner=asset_put,
            actor=actor,
        ),
    )


def _scope_binding(
    scope: CourseReferenceResolutionScope,
) -> CourseReferenceAuthorityScopeBinding:
    owner_scope = CourseReferenceResolutionScopeEvidence(
        scope_id=scope.scope_id,
        course_id=scope.course_id,
        course_title=scope.course_title,
        manifest_id=scope.manifest_id,
        manifest_sha256=scope.manifest_sha256,
        inventory_id=scope.inventory_id,
        total=scope.total,
        ordered_selection_ids=tuple(
            item.selection_id for item in scope.selections
        ),
    )
    owner_selections = tuple(
        CourseReferenceSelectionEvidence(
            scope_id=scope.scope_id,
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
        for item in scope.selections
    )
    return CourseReferenceAuthorityScopeBinding(
        course_scope=scope,
        owner_scope=owner_scope,
        owner_selections=owner_selections,
    )


def _require_binding(
    course_id: str,
    binding: CourseReferenceAuthorityScopeBinding | None,
) -> CourseReferenceAuthorityScopeBinding:
    if binding is None:
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.OWNER_UNAVAILABLE
        )
    if course_id != binding.course_scope.course_id:
        raise CourseReferenceAuthorityFailure(
            CourseReferenceFailureCode.COURSE_NOT_FOUND
        )
    return binding


def _competitors(
    values: tuple[AssetCompetitorDecisionRequest, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            value.asset_observation_id,
            value.disposition.value,
            value.rationale,
        )
        for value in values
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
