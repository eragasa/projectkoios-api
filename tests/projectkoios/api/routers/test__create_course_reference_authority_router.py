from __future__ import annotations

import hashlib
from typing import Any, Literal, cast
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.course_reference_authority import (
    CanonicalAssetPreviewHttpResult,
    CanonicalAssetPutHttpResult,
    CourseReferenceAuthorityFailure,
    CourseReferenceAuthorityHttpActionsCreateResult,
    CourseReferenceQueueHttpResult,
    ReferenceIdentityPreviewHttpResult,
    ReferenceIdentityPutHttpResult,
)
from projectkoios.api.course_reference_authority_models import (
    AssetCompetitorDecisionResponse,
    AssetDecisionPreviewResponse,
    AssetDisposition,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceQueueItemResponse,
    CourseReferenceQueueResponse,
    CourseReferenceScopeResponse,
    CourseReferenceSelectionResponse,
    IdentityDecisionPreviewResponse,
    IdentityDisposition,
)
from projectkoios.api.routers.course_reference_authority import (
    create_course_reference_authority_router,
)


def _cid(kind: str, value: str) -> str:
    return f"{kind}:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _queue() -> CourseReferenceQueueResponse:
    selection_ids = tuple(
        _cid("course-reference-selection", str(i)) for i in (1, 2)
    )
    items = tuple(
        CourseReferenceQueueItemResponse(
            selection=CourseReferenceSelectionResponse(
                scope_id=_cid("course-reference-resolution-scope", "scope"),
                selection_id=selection_id,
                locator_binding_id=_cid(
                    "course-reference-locator-binding", str(index)
                ),
                course_id="dlsu.phy627m.gs1",
                manifest_id=_cid("course-authoring-manifest", "manifest"),
                inventory_id=_cid("course-source-inventory", "inventory"),
                ordinal=index,
                origin=(
                    "preserved-manuscript"
                    if index == 1
                    else "directed-reference-scope"
                ),
                role="manuscript-bibliography",
                display_citekey=f"Example{index}",
                display_citekey_status=(
                    "observed" if index == 1 else "proposed-noncanonical"
                ),
                reference_locator=_cid(
                    "candidate-bibliography-rendered-entry", str(index)
                ),
                previous_selection_id=(
                    None if index == 1 else selection_ids[0]
                ),
                next_selection_id=(selection_ids[1] if index == 1 else None),
            ),
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
                "course-reference-authority-item-revision", str(index)
            ),
        )
        for index, selection_id in enumerate(selection_ids, start=1)
    )
    return CourseReferenceQueueResponse(
        queue_id=_cid("course-reference-authority-queue", "queue"),
        request_id=_cid("course-reference-authority-queue-request", "request"),
        scope=CourseReferenceScopeResponse(
            scope_id=_cid("course-reference-resolution-scope", "scope"),
            course_id="dlsu.phy627m.gs1",
            course_title="Solid State Physics II",
            manifest_id=_cid("course-authoring-manifest", "manifest"),
            manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
            inventory_id=_cid("course-source-inventory", "inventory"),
            total=2,
            ordered_selection_ids=selection_ids,
        ),
        items=items,
        active_authorities=(),
        source_export_result_id=_cid(
            "candidate-bibliography-export-result", "export"
        ),
        render_result_id=_cid("candidate-bibliography-render-result", "render"),
        review_projection_id=_cid("review-projection", "review"),
        state_projection_ids=(),
    )


def _receipt(
    projection: CourseReferenceQueueResponse,
    *,
    item_id: str,
    dimension: Literal["reference-identity", "canonical-asset"],
    disposition: str,
) -> CourseReferenceDecisionReceiptResponse:
    item = next(
        value
        for value in projection.items
        if value.selection.selection_id == item_id
    )
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
        refreshed_queue_id=projection.queue_id,
        refreshed_item_revision_id=item.item_revision_id,
    )


def _actions(
    failure: CourseReferenceFailureCode | None = None,
) -> CourseReferenceAuthorityHttpActionsCreateResult:
    projection = _queue()
    item = projection.items[0]
    queue = Mock()
    identity_preview = Mock()
    asset_preview = Mock()
    identity_put = Mock()
    asset_put = Mock()
    if failure is not None:
        error = CourseReferenceAuthorityFailure(failure)
        for actionizer in (
            queue,
            identity_preview,
            asset_preview,
            identity_put,
            asset_put,
        ):
            actionizer.action.side_effect = error
    else:
        queue.action.return_value = CourseReferenceQueueHttpResult(
            body_json=projection.model_dump_json()
        )
        identity_preview.action.return_value = (
            ReferenceIdentityPreviewHttpResult(
                body_json=IdentityDecisionPreviewResponse(
                    request_id=_cid(
                        "reference-identity-preview-request", "identity"
                    ),
                    result_id=_cid(
                        "reference-identity-preview-result", "identity"
                    ),
                    preview_id=_cid(
                        "reference-identity-decision-preview", "identity"
                    ),
                    selection_id=item.selection.selection_id,
                    disposition=IdentityDisposition.ACCEPT_NEW,
                    target_state_projection_id=None,
                    canonical_citekey=item.selection.display_citekey,
                    alias_citekeys=(),
                    selected_record_match_ids=(),
                    expected_current_decision_id=None,
                    queue_id=projection.queue_id,
                    item_revision_id=item.item_revision_id,
                ).model_dump_json()
            )
        )
        asset_preview.action.return_value = CanonicalAssetPreviewHttpResult(
            body_json=AssetDecisionPreviewResponse(
                request_id=_cid("canonical-asset-preview-request", "asset"),
                result_id=_cid("canonical-asset-preview-result", "asset"),
                preview_id=_cid("canonical-asset-decision-preview", "asset"),
                plan_id=_cid("canonical-asset-evidence-plan", "plan"),
                selection_id=item.selection.selection_id,
                disposition=AssetDisposition.AUTHORIZE,
                identity_state_projection_id=_cid(
                    "reference-state-projection", "identity"
                ),
                competitors=(
                    AssetCompetitorDecisionResponse(
                        asset_observation_id=_cid(
                            "catalog-asset-observation", "asset"
                        ),
                        disposition=AssetDisposition.AUTHORIZE,
                        rationale="Select the verified available asset.",
                    ),
                ),
                selected_asset_observation_id=_cid(
                    "catalog-asset-observation", "asset"
                ),
                expected_current_decision_id=None,
                queue_id=projection.queue_id,
                item_revision_id=item.item_revision_id,
            ).model_dump_json()
        )
        identity_put.action.return_value = ReferenceIdentityPutHttpResult(
            body_json=_receipt(
                projection,
                item_id=item.selection.selection_id,
                dimension="reference-identity",
                disposition="ACCEPT_NEW",
            ).model_dump_json()
        )
        asset_put.action.return_value = CanonicalAssetPutHttpResult(
            body_json=_receipt(
                projection,
                item_id=item.selection.selection_id,
                dimension="canonical-asset",
                disposition="AUTHORIZE",
            ).model_dump_json()
        )
    return CourseReferenceAuthorityHttpActionsCreateResult(
        queue=queue,
        identity_preview=identity_preview,
        asset_preview=asset_preview,
        identity_put=identity_put,
        asset_put=asset_put,
    )


def _client(
    actions: CourseReferenceAuthorityHttpActionsCreateResult,
) -> TestClient:
    app = FastAPI()
    app.include_router(create_course_reference_authority_router(actions))
    return TestClient(app)


def test__router__preserves_complete_ordered_left_projection() -> None:
    actions = _actions()
    expected_body = cast(Mock, actions.queue).action.return_value.body_json
    response = _client(actions).get("/courses/dlsu.phy627m.gs1/references")

    assert response.status_code == 200
    assert response.content == expected_body.encode("utf-8")
    payload = response.json()
    assert payload["control_class"] == "CONTROL"
    assert payload["scope"]["total"] == 2
    assert [item["selection"]["ordinal"] for item in payload["items"]] == [1, 2]
    assert [item["resolution"] for item in payload["items"]] == [
        "rendered-locator-unavailable",
        "rendered-locator-unavailable",
    ]
    assert all(
        not item["allowed_identity_actions"] for item in payload["items"]
    )


def test__router__transports_identity_and_asset_cas_requests() -> None:
    actions = _actions()
    client = _client(actions)
    projection = _queue()
    item = projection.items[0]
    evidence = {
        "expected_queue_id": projection.queue_id,
        "expected_item_revision_id": item.item_revision_id,
        "expected_current_decision_id": None,
    }
    identity_consequence: dict[str, Any] = {
        "disposition": "ACCEPT_NEW",
        "target_state_projection_id": None,
        "canonical_citekey": item.selection.display_citekey,
        "alias_citekeys": [],
        "selected_record_match_ids": [],
    }
    identity_preview = client.post(
        f"/courses/dlsu.phy627m.gs1/references/{item.selection.selection_id}/decision-preview",
        json={**evidence, **identity_consequence},
    )
    asset_consequence = {
        "expected_identity_state_projection_id": _cid(
            "reference-state-projection", "identity"
        ),
        "disposition": "AUTHORIZE",
        "competitors": [
            {
                "asset_observation_id": _cid(
                    "catalog-asset-observation", "asset"
                ),
                "disposition": "AUTHORIZE",
                "rationale": "Select the verified available asset.",
            }
        ],
    }
    asset_preview = client.post(
        f"/courses/dlsu.phy627m.gs1/references/{item.selection.selection_id}/asset-decision-preview",
        json={**evidence, **asset_consequence},
    )
    assert identity_preview.status_code == 200
    assert asset_preview.status_code == 200

    decision_metadata = {
        "idempotency_key": "test-decision-1",
        "rationale": "Explicit curator review.",
        "decided_at": "2026-10-11T06:00:00Z",
    }
    identity = client.put(
        f"/courses/dlsu.phy627m.gs1/references/{item.selection.selection_id}/decision",
        json={
            **evidence,
            **identity_consequence,
            **decision_metadata,
            "expected_preview_id": identity_preview.json()["preview_id"],
            "expected_preview_result_id": identity_preview.json()["result_id"],
        },
    )
    asset = client.put(
        f"/courses/dlsu.phy627m.gs1/references/{item.selection.selection_id}/asset-decision",
        json={
            **evidence,
            **asset_consequence,
            **decision_metadata,
            "expected_preview_id": asset_preview.json()["preview_id"],
            "expected_preview_result_id": asset_preview.json()["result_id"],
            "expected_asset_plan_id": asset_preview.json()["plan_id"],
        },
    )

    assert identity.status_code == 200
    assert identity.json()["disposition"] == "ACCEPT_NEW"
    assert asset.status_code == 200
    assert asset.json()["disposition"] == "AUTHORIZE"
    identity_preview_request = cast(
        Mock, actions.identity_preview
    ).action.call_args.kwargs["request"]
    asset_preview_request = cast(
        Mock, actions.asset_preview
    ).action.call_args.kwargs["request"]
    identity_request = cast(Mock, actions.identity_put).action.call_args.kwargs[
        "request"
    ]
    asset_request = cast(Mock, actions.asset_put).action.call_args.kwargs[
        "request"
    ]
    assert identity_preview_request.body.canonical_citekey == (
        item.selection.display_citekey
    )
    assert asset_preview_request.body.competitors == (
        asset_request.body.competitors
    )
    assert identity_request.body.expected_queue_id == projection.queue_id
    assert asset_request.body.competitors[0].disposition.value == "AUTHORIZE"


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (CourseReferenceFailureCode.COURSE_NOT_FOUND, 404),
        (CourseReferenceFailureCode.ITEM_NOT_FOUND, 404),
        (CourseReferenceFailureCode.EVIDENCE_STALE, 409),
        (CourseReferenceFailureCode.REVISION_STALE, 409),
        (CourseReferenceFailureCode.TARGET_STALE, 409),
        (CourseReferenceFailureCode.CONCURRENT_DECISION, 409),
        (CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT, 409),
        (CourseReferenceFailureCode.INVALID_DISPOSITION, 409),
        (CourseReferenceFailureCode.OWNER_MALFORMED, 502),
        (CourseReferenceFailureCode.OWNER_UNAVAILABLE, 503),
    ],
)
def test__router__maps_typed_failures_without_owner_detail(
    code: CourseReferenceFailureCode,
    status_code: int,
) -> None:
    response = _client(_actions(failure=code)).get(
        "/courses/dlsu.phy627m.gs1/references"
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code.value
    assert set(response.json()) == {"code", "detail"}
