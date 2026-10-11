from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal, cast
from unittest.mock import Mock

import pytest
from projectkoios.api.config import (
    CourseReferenceAuthorityActorConfiguration,
    CourseReferenceAuthorityConfiguration,
)
from projectkoios.api.course_reference_authority import (
    CanonicalAssetPreviewHttpActionizer,
    CanonicalAssetPreviewHttpRequest,
    CanonicalAssetPutHttpActionizer,
    CanonicalAssetPutHttpRequest,
    CourseReferenceAuthorityFailure,
    CourseReferenceAuthorityHttpActionsCreateActionizer,
    CourseReferenceAuthorityHttpActionsCreateRequest,
    CourseReferenceAuthorityScopeBinding,
    CourseReferenceQueueHttpActionizer,
    CourseReferenceQueueHttpRequest,
    ReferenceIdentityPreviewHttpActionizer,
    ReferenceIdentityPreviewHttpRequest,
    ReferenceIdentityPutHttpActionizer,
    ReferenceIdentityPutHttpRequest,
)
from projectkoios.api.course_reference_authority_models import (
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
    IdentityDecisionPreviewRequest,
    IdentityDecisionPreviewResponse,
    IdentityDecisionRequest,
    IdentityDisposition,
)
from projectkoios.courses.reference_resolution import (
    CourseReferenceDisplayCitekeyStatus,
    CourseReferenceLocatorBinding,
    CourseReferenceResolutionScope,
    CourseReferenceRole,
    CourseReferenceSelection,
    CourseReferenceSelectionOrigin,
)
from projectkoios.references.catalog import ReferenceCatalog
from projectkoios.references.courses.authority.scope import (
    CourseDisplayCitekeyStatus,
    CourseReferenceResolutionScopeEvidence,
    CourseReferenceSelectionEvidence,
)
from projectkoios.references.courses.authority.scope import (
    CourseReferenceRole as OwnerCourseReferenceRole,
)
from projectkoios.references.courses.authority.scope import (
    CourseReferenceSelectionOrigin as OwnerCourseReferenceSelectionOrigin,
)
from projectkoios.references.courses.authority.service import (
    CourseReferenceAuthorityFailureReason,
    CourseReferenceAuthorityServiceError,
)
from projectkoios.references.courses.runtime.configuration import (
    CourseReferenceAuthorityBibliographySource,
    CourseReferenceAuthorityRuntimeConfiguration,
)
from projectkoios.references.courses.transport.asset import (
    CanonicalAssetPreviewTransportActionizer,
    CanonicalAssetPreviewTransportResult,
    CanonicalAssetPutTransportActionizer,
    CanonicalAssetPutTransportResult,
)
from projectkoios.references.courses.transport.identity import (
    ReferenceIdentityPreviewTransportActionizer,
    ReferenceIdentityPreviewTransportResult,
    ReferenceIdentityPutTransportActionizer,
    ReferenceIdentityPutTransportResult,
)
from projectkoios.references.courses.transport.queue import (
    CourseReferenceQueueTransportActionizer,
    CourseReferenceQueueTransportResult,
)
from projectkoios.references.path_safety import RootStorageClass


def _cid(kind: str, value: str) -> str:
    return f"{kind}:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _scope() -> CourseReferenceResolutionScope:
    manifest_id = _cid("course-authoring-manifest", "manifest")
    inventory_id = _cid("course-source-inventory", "inventory")
    locator = CourseReferenceLocatorBinding(
        ordinal=1,
        display_citekey="Example2026",
        display_citekey_status=(
            CourseReferenceDisplayCitekeyStatus.PROPOSED_NONCANONICAL
        ),
        reference_locator=_cid("candidate-bibliography-entry", "entry"),
    )
    selection = CourseReferenceSelection(
        course_id="dlsu.phy627m.gs1",
        manifest_id=manifest_id,
        inventory_id=inventory_id,
        ordinal=1,
        origin=CourseReferenceSelectionOrigin.DIRECTED_REFERENCE_SCOPE,
        role=CourseReferenceRole.MANUSCRIPT_BIBLIOGRAPHY,
        display_citekey="Example2026",
        display_citekey_status=(
            CourseReferenceDisplayCitekeyStatus.PROPOSED_NONCANONICAL
        ),
        reference_locator=locator.reference_locator,
        locator_binding_id=locator.binding_id,
    )
    return CourseReferenceResolutionScope(
        course_id="dlsu.phy627m.gs1",
        course_title="Solid State Physics II",
        manifest_id=manifest_id,
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        inventory_id=inventory_id,
        selections=(selection,),
    )


def _binding() -> CourseReferenceAuthorityScopeBinding:
    scope = _scope()
    selection = scope.selections[0]
    owner_scope = CourseReferenceResolutionScopeEvidence(
        scope_id=scope.scope_id,
        course_id=scope.course_id,
        course_title=scope.course_title,
        manifest_id=scope.manifest_id,
        manifest_sha256=scope.manifest_sha256,
        inventory_id=scope.inventory_id,
        total=scope.total,
        ordered_selection_ids=(selection.selection_id,),
    )
    owner_selection = CourseReferenceSelectionEvidence(
        scope_id=scope.scope_id,
        selection_id=selection.selection_id,
        locator_binding_id=selection.locator_binding_id,
        course_id=selection.course_id,
        manifest_id=selection.manifest_id,
        inventory_id=selection.inventory_id,
        ordinal=selection.ordinal,
        origin=OwnerCourseReferenceSelectionOrigin(selection.origin.value),
        role=OwnerCourseReferenceRole(selection.role.value),
        display_citekey=selection.display_citekey,
        display_citekey_status=CourseDisplayCitekeyStatus(
            selection.display_citekey_status.value
        ),
        reference_locator=selection.reference_locator,
    )
    return CourseReferenceAuthorityScopeBinding(
        course_scope=scope,
        owner_scope=owner_scope,
        owner_selections=(owner_selection,),
    )


def _actor() -> CourseReferenceAuthorityActorConfiguration:
    return CourseReferenceAuthorityActorConfiguration(
        actor_id="control-curator",
        verification_record_id=_cid("actor-verification", "curator"),
        verification_method="authenticated-control-session",
    )


def _queue_response() -> CourseReferenceQueueResponse:
    binding = _binding()
    scope = binding.course_scope
    selection = scope.selections[0]
    queue_id = _cid("course-reference-authority-queue", "queue")
    selection_response = CourseReferenceSelectionResponse(
        scope_id=scope.scope_id,
        selection_id=selection.selection_id,
        locator_binding_id=selection.locator_binding_id,
        course_id=selection.course_id,
        manifest_id=selection.manifest_id,
        inventory_id=selection.inventory_id,
        ordinal=selection.ordinal,
        origin=selection.origin.value,
        role=selection.role.value,
        display_citekey=selection.display_citekey,
        display_citekey_status=selection.display_citekey_status.value,
        reference_locator=selection.reference_locator,
        previous_selection_id=None,
        next_selection_id=None,
    )
    item = CourseReferenceQueueItemResponse(
        selection=selection_response,
        resolution="rendered-locator-unavailable",
        candidate=None,
        observations=(),
        rendered_entry=None,
        record_matches=(),
        assets=(),
        current_identity_decisions=(),
        current_asset_decision=None,
        active_authority=None,
        allowed_identity_actions=(),
        allowed_asset_actions=(),
        item_revision_id=_cid(
            "course-reference-authority-item-revision", "item"
        ),
    )
    return CourseReferenceQueueResponse(
        request_id=_cid("course-reference-authority-queue-request", "request"),
        queue_id=queue_id,
        source_export_result_id=_cid(
            "candidate-bibliography-export-result", "export"
        ),
        render_result_id=_cid("candidate-bibliography-render-result", "render"),
        review_projection_id=_cid("review-projection", "review"),
        state_projection_ids=(),
        scope=CourseReferenceScopeResponse(
            scope_id=scope.scope_id,
            course_id=scope.course_id,
            course_title=scope.course_title,
            manifest_id=scope.manifest_id,
            manifest_sha256=scope.manifest_sha256,
            inventory_id=scope.inventory_id,
            total=scope.total,
            ordered_selection_ids=(selection.selection_id,),
        ),
        items=(item,),
        active_authorities=(),
    )


def _identity_preview_response() -> IdentityDecisionPreviewResponse:
    queue = _queue_response()
    item = queue.items[0]
    return IdentityDecisionPreviewResponse(
        request_id=_cid("reference-identity-preview-request", "request"),
        result_id=_cid("reference-identity-preview-result", "result"),
        preview_id=_cid("reference-identity-decision-preview", "preview"),
        selection_id=item.selection.selection_id,
        disposition=IdentityDisposition.ACCEPT_NEW,
        target_state_projection_id=None,
        canonical_citekey=item.selection.display_citekey,
        alias_citekeys=(),
        selected_record_match_ids=(),
        expected_current_decision_id=None,
        queue_id=queue.queue_id,
        item_revision_id=item.item_revision_id,
    )


def _asset_preview_response() -> AssetDecisionPreviewResponse:
    queue = _queue_response()
    item = queue.items[0]
    asset_id = _cid("catalog-asset-observation", "asset")
    return AssetDecisionPreviewResponse(
        request_id=_cid("canonical-asset-preview-request", "request"),
        result_id=_cid("canonical-asset-preview-result", "result"),
        preview_id=_cid("canonical-asset-decision-preview", "preview"),
        plan_id=_cid("canonical-asset-evidence-plan", "plan"),
        selection_id=item.selection.selection_id,
        disposition=AssetDisposition.AUTHORIZE,
        identity_state_projection_id=_cid(
            "reference-state-projection", "identity"
        ),
        competitors=(
            AssetCompetitorDecisionResponse(
                asset_observation_id=asset_id,
                disposition=AssetDisposition.AUTHORIZE,
                rationale="Select the verified source bytes.",
            ),
        ),
        selected_asset_observation_id=asset_id,
        expected_current_decision_id=None,
        queue_id=queue.queue_id,
        item_revision_id=item.item_revision_id,
    )


def _receipt(
    dimension: Literal["reference-identity", "canonical-asset"],
    disposition: str,
) -> CourseReferenceDecisionReceiptResponse:
    queue = _queue_response()
    return CourseReferenceDecisionReceiptResponse(
        receipt_id=_cid("reference-authority-decision-receipt", dimension),
        result_id=_cid("reference-authority-decision-result", dimension),
        put_request_id=_cid("reference-authority-put-request", dimension),
        decision_append_request_id=_cid(
            "append-reference-authority-decision-request", dimension
        ),
        preview_id=_cid("reference-authority-decision-preview", dimension),
        decision_id=_cid("review-decision", dimension),
        dimension=dimension,
        disposition=disposition,
        state_projection_id=None,
        current_decision_id=_cid("review-decision", dimension),
        current_state_projection_id=None,
        refreshed_queue_id=queue.queue_id,
        refreshed_item_revision_id=queue.items[0].item_revision_id,
    )


def test__five_http_actions_forward_exact_trusted_transport_inputs() -> None:
    binding = _binding()
    actor = _actor()
    queue_body = _queue_response()
    identity_preview_body = _identity_preview_response()
    asset_preview_body = _asset_preview_response()
    identity_receipt = _receipt("reference-identity", "ACCEPT_NEW")
    asset_receipt = _receipt("canonical-asset", "AUTHORIZE")

    queue_owner = cast(CourseReferenceQueueTransportActionizer, Mock())
    queue_owner.action.return_value = CourseReferenceQueueTransportResult(
        body_json=queue_body.model_dump_json()
    )
    identity_preview_owner = cast(
        ReferenceIdentityPreviewTransportActionizer, Mock()
    )
    identity_preview_owner.action.return_value = (
        ReferenceIdentityPreviewTransportResult(
            body_json=identity_preview_body.model_dump_json()
        )
    )
    asset_preview_owner = cast(CanonicalAssetPreviewTransportActionizer, Mock())
    asset_preview_owner.action.return_value = (
        CanonicalAssetPreviewTransportResult(
            body_json=asset_preview_body.model_dump_json()
        )
    )
    identity_put_owner = cast(ReferenceIdentityPutTransportActionizer, Mock())
    identity_put_owner.action.return_value = (
        ReferenceIdentityPutTransportResult(
            body_json=identity_receipt.model_dump_json()
        )
    )
    asset_put_owner = cast(CanonicalAssetPutTransportActionizer, Mock())
    asset_put_owner.action.return_value = CanonicalAssetPutTransportResult(
        body_json=asset_receipt.model_dump_json()
    )

    queue_action = CourseReferenceQueueHttpActionizer(
        binding=binding,
        owner=queue_owner,
    )
    identity_preview_action = ReferenceIdentityPreviewHttpActionizer(
        binding=binding,
        owner=identity_preview_owner,
    )
    asset_preview_action = CanonicalAssetPreviewHttpActionizer(
        binding=binding,
        owner=asset_preview_owner,
    )
    identity_put_action = ReferenceIdentityPutHttpActionizer(
        binding=binding,
        owner=identity_put_owner,
        actor=actor,
    )
    asset_put_action = CanonicalAssetPutHttpActionizer(
        binding=binding,
        owner=asset_put_owner,
        actor=actor,
    )
    queue_result = queue_action.action(
        request=CourseReferenceQueueHttpRequest(
            course_id=queue_body.scope.course_id
        )
    )
    queue = CourseReferenceQueueResponse.model_validate_json(
        queue_result.body_json
    )
    item = queue.items[0]
    identity_preview_request = IdentityDecisionPreviewRequest(
        expected_queue_id=queue.queue_id,
        expected_item_revision_id=item.item_revision_id,
        disposition=IdentityDisposition.ACCEPT_NEW,
        canonical_citekey=item.selection.display_citekey,
        alias_citekeys=(),
        selected_record_match_ids=(),
    )
    identity_preview_result = identity_preview_action.action(
        request=ReferenceIdentityPreviewHttpRequest(
            course_id=queue.scope.course_id,
            item_id=item.selection.selection_id,
            body=identity_preview_request,
        )
    )
    identity_preview = IdentityDecisionPreviewResponse.model_validate_json(
        identity_preview_result.body_json
    )
    asset_competitors = (
        AssetCompetitorDecisionRequest(
            asset_observation_id=asset_preview_body.competitors[
                0
            ].asset_observation_id,
            disposition=AssetDisposition.AUTHORIZE,
            rationale="Select the verified source bytes.",
        ),
    )
    asset_preview_request = AssetDecisionPreviewRequest(
        expected_queue_id=queue.queue_id,
        expected_item_revision_id=item.item_revision_id,
        expected_identity_state_projection_id=(
            asset_preview_body.identity_state_projection_id
        ),
        disposition=AssetDisposition.AUTHORIZE,
        competitors=asset_competitors,
    )
    asset_preview_result = asset_preview_action.action(
        request=CanonicalAssetPreviewHttpRequest(
            course_id=queue.scope.course_id,
            item_id=item.selection.selection_id,
            body=asset_preview_request,
        )
    )
    asset_preview = AssetDecisionPreviewResponse.model_validate_json(
        asset_preview_result.body_json
    )
    identity_put_result = identity_put_action.action(
        request=ReferenceIdentityPutHttpRequest(
            course_id=queue.scope.course_id,
            item_id=item.selection.selection_id,
            body=IdentityDecisionRequest(
                idempotency_key="identity-1",
                expected_queue_id=queue.queue_id,
                expected_item_revision_id=item.item_revision_id,
                expected_preview_id=identity_preview.preview_id,
                expected_preview_result_id=identity_preview.result_id,
                disposition=IdentityDisposition.ACCEPT_NEW,
                canonical_citekey=item.selection.display_citekey,
                alias_citekeys=(),
                selected_record_match_ids=(),
                rationale="Accept the reviewed identity.",
                decided_at="2026-10-11T06:00:00Z",
            ),
        )
    )
    asset_put_result = asset_put_action.action(
        request=CanonicalAssetPutHttpRequest(
            course_id=queue.scope.course_id,
            item_id=item.selection.selection_id,
            body=AssetDecisionRequest(
                idempotency_key="asset-1",
                expected_queue_id=queue.queue_id,
                expected_item_revision_id=item.item_revision_id,
                expected_preview_id=asset_preview.preview_id,
                expected_preview_result_id=asset_preview.result_id,
                expected_identity_state_projection_id=(
                    asset_preview.identity_state_projection_id
                ),
                expected_asset_plan_id=asset_preview.plan_id,
                disposition=AssetDisposition.AUTHORIZE,
                competitors=asset_competitors,
                rationale="Authorize the reviewed source bytes.",
                decided_at="2026-10-11T06:00:01Z",
            ),
        )
    )

    queue_owner_request = queue_owner.action.call_args.kwargs["request"]
    identity_owner_request = identity_put_owner.action.call_args.kwargs[
        "request"
    ]
    asset_owner_request = asset_put_owner.action.call_args.kwargs["request"]
    assert queue == queue_body
    assert queue_result.body_json == queue_body.model_dump_json()
    assert identity_preview_result.body_json == (
        identity_preview_body.model_dump_json()
    )
    assert (
        asset_preview_result.body_json == asset_preview_body.model_dump_json()
    )
    assert identity_put_result.body_json == identity_receipt.model_dump_json()
    assert asset_put_result.body_json == asset_receipt.model_dump_json()
    assert queue_owner_request.scope is binding.owner_scope
    assert queue_owner_request.selections is binding.owner_selections
    assert (
        identity_owner_request.expected_preview_id
        == identity_preview.preview_id
    )
    assert identity_owner_request.actor_id == actor.actor_id
    assert identity_owner_request.actor_verification_record_id == (
        actor.verification_record_id
    )
    assert asset_owner_request.competitors == (
        (
            asset_competitors[0].asset_observation_id,
            "AUTHORIZE",
            asset_competitors[0].rationale,
        ),
    )
    assert asset_owner_request.actor_verification_method == (
        actor.verification_method
    )


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        (
            CourseReferenceAuthorityFailureReason.COURSE_NOT_FOUND,
            CourseReferenceFailureCode.COURSE_NOT_FOUND,
        ),
        (
            CourseReferenceAuthorityFailureReason.ITEM_NOT_FOUND,
            CourseReferenceFailureCode.ITEM_NOT_FOUND,
        ),
        (
            CourseReferenceAuthorityFailureReason.EVIDENCE_STALE,
            CourseReferenceFailureCode.EVIDENCE_STALE,
        ),
        (
            CourseReferenceAuthorityFailureReason.REVISION_STALE,
            CourseReferenceFailureCode.REVISION_STALE,
        ),
        (
            CourseReferenceAuthorityFailureReason.TARGET_STALE,
            CourseReferenceFailureCode.TARGET_STALE,
        ),
        (
            CourseReferenceAuthorityFailureReason.CONCURRENT_DECISION,
            CourseReferenceFailureCode.CONCURRENT_DECISION,
        ),
        (
            CourseReferenceAuthorityFailureReason.IDEMPOTENCY_CONFLICT,
            CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT,
        ),
        (
            CourseReferenceAuthorityFailureReason.INVALID_DISPOSITION,
            CourseReferenceFailureCode.INVALID_DISPOSITION,
        ),
        (
            CourseReferenceAuthorityFailureReason.OWNER_MALFORMED,
            CourseReferenceFailureCode.OWNER_MALFORMED,
        ),
        (
            CourseReferenceAuthorityFailureReason.OWNER_UNAVAILABLE,
            CourseReferenceFailureCode.OWNER_UNAVAILABLE,
        ),
    ],
)
def test__owner_failures_are_mapped_without_private_detail(
    reason: CourseReferenceAuthorityFailureReason,
    code: CourseReferenceFailureCode,
) -> None:
    owner = cast(CourseReferenceQueueTransportActionizer, Mock())
    owner.action.side_effect = CourseReferenceAuthorityServiceError(
        reason,
        "private owner detail",
    )
    action = CourseReferenceQueueHttpActionizer(
        binding=_binding(),
        owner=owner,
    )

    with pytest.raises(CourseReferenceAuthorityFailure) as captured:
        action.action(
            request=CourseReferenceQueueHttpRequest(
                course_id="dlsu.phy627m.gs1"
            )
        )

    assert captured.value.code is code
    assert str(captured.value) == code.value
    assert "private" not in str(captured.value)


def test__malformed_owner_json_is_a_typed_boundary_failure() -> None:
    owner = cast(CourseReferenceQueueTransportActionizer, Mock())
    owner.action.return_value = CourseReferenceQueueTransportResult(
        body_json='{"not":"a queue"}'
    )
    action = CourseReferenceQueueHttpActionizer(
        binding=_binding(),
        owner=owner,
    )

    with pytest.raises(CourseReferenceAuthorityFailure) as captured:
        action.action(
            request=CourseReferenceQueueHttpRequest(
                course_id="dlsu.phy627m.gs1"
            )
        )

    assert captured.value.code is CourseReferenceFailureCode.OWNER_MALFORMED


def test__unconfigured_factory_exposes_five_unavailable_actions() -> None:
    actions = CourseReferenceAuthorityHttpActionsCreateActionizer().action(
        request=CourseReferenceAuthorityHttpActionsCreateRequest(
            scope=None,
            configuration=None,
            actor=None,
        )
    )

    with pytest.raises(CourseReferenceAuthorityFailure) as captured:
        actions.queue.action(
            request=CourseReferenceQueueHttpRequest(
                course_id="dlsu.phy627m.gs1"
            )
        )

    assert captured.value.code is CourseReferenceFailureCode.OWNER_UNAVAILABLE
    assert actions.identity_preview is not None
    assert actions.asset_preview is not None
    assert actions.identity_put is not None
    assert actions.asset_put is not None


def test__optional_private_exact_fourteen_api_projection(
    tmp_path: Path,
) -> None:
    declaration_path = os.environ.get(
        "PROJECTKOIOS_REFERENCE_AUTHORITY_PRIVATE_SMOKE_JSON"
    )
    if declaration_path is None:
        pytest.skip("private authority smoke declaration is not configured")
    declaration = json.loads(Path(declaration_path).read_text(encoding="utf-8"))
    raw_scope = declaration["scope"]
    manifest_id = raw_scope["manifest_id"]
    inventory_id = raw_scope["inventory_id"]
    selections = tuple(
        CourseReferenceSelection(
            course_id=raw_scope["course_id"],
            manifest_id=manifest_id,
            inventory_id=inventory_id,
            ordinal=item["ordinal"],
            origin=CourseReferenceSelectionOrigin(item["origin"]),
            role=CourseReferenceRole(item["role"]),
            display_citekey=item["display_citekey"],
            display_citekey_status=CourseReferenceDisplayCitekeyStatus(
                item["display_citekey_status"]
            ),
            reference_locator=item["reference_locator"],
            locator_binding_id=item["locator_binding_id"],
        )
        for item in raw_scope["selections"]
    )
    scope = CourseReferenceResolutionScope(
        course_id=raw_scope["course_id"],
        course_title=raw_scope["course_title"],
        manifest_id=manifest_id,
        manifest_sha256=raw_scope["manifest_sha256"],
        inventory_id=inventory_id,
        selections=selections,
    )
    assert scope.scope_id == raw_scope["scope_id"]
    catalog_path = tmp_path / "references.sqlite3"
    ReferenceCatalog(
        catalog_path,
        storage_class=RootStorageClass.LOCAL,
    ).initialize()
    composition = CourseReferenceAuthorityConfiguration(
        scope=scope,
        runtime=CourseReferenceAuthorityRuntimeConfiguration(
            course_id=scope.course_id,
            catalog_path=catalog_path,
            catalog_storage_class=RootStorageClass.LOCAL,
            bibliography_sources=tuple(
                CourseReferenceAuthorityBibliographySource(
                    collection_id=item["collection_id"],
                    bibliography_path=Path(item["path"]),
                    source_id=item["source_id"],
                    asserted_source_revision=item["asserted_source_revision"],
                    source_path=item["source_path"],
                    storage_class=RootStorageClass(item["storage_class"]),
                )
                for item in declaration["sources"]
            ),
        ),
        actor=_actor(),
    )
    actions = CourseReferenceAuthorityHttpActionsCreateActionizer().action(
        request=CourseReferenceAuthorityHttpActionsCreateRequest(
            scope=composition.scope,
            configuration=composition.runtime,
            actor=composition.actor,
        )
    )
    projection_result = actions.queue.action(
        request=CourseReferenceQueueHttpRequest(course_id=scope.course_id)
    )
    projection = CourseReferenceQueueResponse.model_validate_json(
        projection_result.body_json
    )

    assert projection.scope.total == 14
    assert (
        projection.render_result_id == declaration["expected_render_result_id"]
    )
    assert tuple(item.selection.selection_id for item in projection.items) == (
        projection.scope.ordered_selection_ids
    )
    assert [item.selection.display_citekey for item in projection.items] == [
        "deBroglie1925",
        "Shankar1994",
        "Hellmann1937",
        "Feynman1939",
        "Xiao2010",
        "kittel2005",
        "simon2013",
        "ashcroftMermin1976",
        "marder2010",
        "szeNg2007",
        "neamen2003",
        "szeLee2012",
        "yuCardona2010",
        "rudan2015",
    ]
    assert all(item.resolution == "ready" for item in projection.items)
