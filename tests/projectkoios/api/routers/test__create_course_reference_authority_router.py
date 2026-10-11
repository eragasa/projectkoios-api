from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.course_reference_authority import (
    CourseReferenceAuthorityFailure,
)
from projectkoios.api.course_reference_authority_models import (
    AssetCompetitorDecisionResponse,
    AssetDecisionPreviewRequest,
    AssetDecisionPreviewResponse,
    AssetDecisionRequest,
    CourseReferenceDecisionReceiptResponse,
    CourseReferenceFailureCode,
    CourseReferenceQueueItemResponse,
    CourseReferenceQueueResponse,
    CourseReferenceScopeResponse,
    CourseReferenceSelectionResponse,
    IdentityDecisionPreviewRequest,
    IdentityDecisionPreviewResponse,
    IdentityDecisionRequest,
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


@dataclass
class _Provider:
    projection: CourseReferenceQueueResponse = field(default_factory=_queue)
    failure: CourseReferenceFailureCode | None = None
    identity_preview_requests: list[
        tuple[str, str, IdentityDecisionPreviewRequest]
    ] = field(default_factory=list)
    asset_preview_requests: list[
        tuple[str, str, AssetDecisionPreviewRequest]
    ] = field(default_factory=list)
    identity_requests: list[tuple[str, str, IdentityDecisionRequest]] = field(
        default_factory=list
    )
    asset_requests: list[tuple[str, str, AssetDecisionRequest]] = field(
        default_factory=list
    )

    def queue(self, course_id: str) -> CourseReferenceQueueResponse:
        self._fail()
        assert course_id == "dlsu.phy627m.gs1"
        return self.projection

    def preview_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionPreviewRequest,
    ) -> IdentityDecisionPreviewResponse:
        self._fail()
        self.identity_preview_requests.append((course_id, item_id, request))
        return IdentityDecisionPreviewResponse(
            request_id=_cid("reference-identity-preview-request", "identity"),
            result_id=_cid("reference-identity-preview-result", "identity"),
            preview_id=_cid("reference-identity-decision-preview", "identity"),
            selection_id=item_id,
            disposition=request.disposition,
            target_state_projection_id=request.target_state_projection_id,
            canonical_citekey=request.canonical_citekey,
            alias_citekeys=request.alias_citekeys,
            selected_record_match_ids=request.selected_record_match_ids,
            expected_current_decision_id=request.expected_current_decision_id,
            queue_id=request.expected_queue_id,
            item_revision_id=request.expected_item_revision_id,
        )

    def preview_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionPreviewRequest,
    ) -> AssetDecisionPreviewResponse:
        self._fail()
        self.asset_preview_requests.append((course_id, item_id, request))
        authorized = tuple(
            item.asset_observation_id
            for item in request.competitors
            if item.disposition.value == "AUTHORIZE"
        )
        return AssetDecisionPreviewResponse(
            request_id=_cid("canonical-asset-preview-request", "asset"),
            result_id=_cid("canonical-asset-preview-result", "asset"),
            preview_id=_cid("canonical-asset-decision-preview", "asset"),
            plan_id=_cid("canonical-asset-evidence-plan", "plan"),
            selection_id=item_id,
            disposition=request.disposition,
            identity_state_projection_id=(
                request.expected_identity_state_projection_id
            ),
            competitors=tuple(
                AssetCompetitorDecisionResponse(
                    asset_observation_id=item.asset_observation_id,
                    disposition=item.disposition,
                    rationale=item.rationale,
                )
                for item in request.competitors
            ),
            selected_asset_observation_id=(
                authorized[0] if len(authorized) == 1 else None
            ),
            expected_current_decision_id=request.expected_current_decision_id,
            queue_id=request.expected_queue_id,
            item_revision_id=request.expected_item_revision_id,
        )

    def decide_identity(
        self,
        course_id: str,
        item_id: str,
        request: IdentityDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        self._fail()
        self.identity_requests.append((course_id, item_id, request))
        return self._receipt(item_id, "reference-identity", "ACCEPT_NEW")

    def decide_asset(
        self,
        course_id: str,
        item_id: str,
        request: AssetDecisionRequest,
    ) -> CourseReferenceDecisionReceiptResponse:
        self._fail()
        self.asset_requests.append((course_id, item_id, request))
        return self._receipt(item_id, "canonical-asset", "AUTHORIZE")

    def _fail(self) -> None:
        if self.failure is not None:
            raise CourseReferenceAuthorityFailure(self.failure)

    def _receipt(
        self,
        item_id: str,
        dimension: str,
        disposition: str,
    ) -> CourseReferenceDecisionReceiptResponse:
        item = next(
            value
            for value in self.projection.items
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
            refreshed_queue_id=self.projection.queue_id,
            refreshed_item_revision_id=item.item_revision_id,
        )


def _client(provider: _Provider) -> TestClient:
    app = FastAPI()
    app.include_router(create_course_reference_authority_router(provider))
    return TestClient(app)


def test__router__preserves_complete_ordered_left_projection() -> None:
    response = _client(_Provider()).get("/courses/dlsu.phy627m.gs1/references")

    assert response.status_code == 200
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
    provider = _Provider()
    client = _client(provider)
    item = provider.projection.items[0]
    evidence = {
        "expected_queue_id": provider.projection.queue_id,
        "expected_item_revision_id": item.item_revision_id,
        "expected_current_decision_id": None,
    }
    identity_consequence = {
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
    assert provider.identity_preview_requests[0][2].canonical_citekey == (
        item.selection.display_citekey
    )
    assert provider.asset_preview_requests[0][2].competitors == (
        provider.asset_requests[0][2].competitors
    )
    assert provider.identity_requests[0][2].expected_queue_id == (
        provider.projection.queue_id
    )
    assert provider.asset_requests[0][2].competitors[0].disposition.value == (
        "AUTHORIZE"
    )


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
    response = _client(_Provider(failure=code)).get(
        "/courses/dlsu.phy627m.gs1/references"
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code.value
    assert set(response.json()) == {"code", "detail"}
