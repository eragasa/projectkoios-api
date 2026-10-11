from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from projectkoios.api.config import CourseReferenceAuthorityConfiguration
from projectkoios.api.course_reference_authority import (
    CourseReferenceAuthorityFailure,
    ReferencesCourseReferenceAuthorityProvider,
    open_references_course_reference_authority_provider,
)
from projectkoios.api.course_reference_authority_models import (
    AssetCompetitorDecisionRequest,
    AssetDecisionRequest,
    AssetDisposition,
    CourseReferenceFailureCode,
    IdentityDecisionRequest,
    IdentityDisposition,
    ReviewActorRequest,
)
from projectkoios.courses.reference_resolution import (
    CourseReferenceDisplayCitekeyStatus,
    CourseReferenceLocatorBinding,
    CourseReferenceResolutionScope,
    CourseReferenceRole,
    CourseReferenceSelection,
    CourseReferenceSelectionOrigin,
)
from projectkoios.references.biblatex import load_bibliography
from projectkoios.references.candidate_bibliography import (
    CandidateBibliographyExportRequest,
    CandidateBibliographyRenderer,
    CandidateBibliographyRenderRequest,
    CandidateBibliographySourceDeclaration,
)
from projectkoios.references.catalog import ReferenceCatalog
from projectkoios.references.course_reference_authority import (
    CourseReferenceAuthorityOwnerEvidence,
    CourseReferenceAuthorityService,
    ReferenceAssetAuthorityEvidence,
    RenderedEntryCandidateBinding,
    RuntimeAssetAvailability,
)
from projectkoios.references.course_reference_authority_runtime import (
    CourseReferenceAuthorityBibliographySource,
    CourseReferenceAuthorityRuntimeConfiguration,
)
from projectkoios.references.identity import (
    ReferenceCandidate,
    SourceBibliographyObservation,
)
from projectkoios.references.models import SourceAssetRecord
from projectkoios.references.path_safety import RootStorageClass


def _cid(kind: str, value: str) -> str:
    return f"{kind}:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


@dataclass
class _OwnerProvider:
    render: object
    candidates: tuple[ReferenceCandidate, ...]
    observations: tuple[SourceBibliographyObservation, ...]
    bindings: tuple[RenderedEntryCandidateBinding, ...]
    assets: tuple[ReferenceAssetAuthorityEvidence, ...] = ()

    def load_course_reference_authority_evidence(
        self,
        *,
        scope: object,
        catalog_candidates: tuple[ReferenceCandidate, ...],
        catalog_observations: tuple[SourceBibliographyObservation, ...],
        catalog_assets: tuple[SourceAssetRecord, ...],
    ) -> CourseReferenceAuthorityOwnerEvidence:
        del scope, catalog_assets
        candidates = {
            item.candidate_id: item
            for item in (*catalog_candidates, *self.candidates)
        }
        observations = {
            item.observation_id: item
            for item in (*catalog_observations, *self.observations)
        }
        return CourseReferenceAuthorityOwnerEvidence(
            render_result=self.render,
            candidates=tuple(
                sorted(candidates.values(), key=lambda item: item.candidate_id)
            ),
            observations=tuple(
                sorted(
                    observations.values(),
                    key=lambda item: item.observation_id,
                )
            ),
            rendered_candidate_bindings=self.bindings,
            record_discrepancies=(),
            assets=self.assets,
        )


def _provider(
    tmp_path: Path,
) -> tuple[
    ReferencesCourseReferenceAuthorityProvider,
    ReferenceCatalog,
    _OwnerProvider,
    ReferenceCandidate,
]:
    bibliography = tmp_path / "candidate.bib"
    bibliography.write_text(
        "@book{Example2026, title={Example Work}, author={Curator, Casey}, "
        "year={2026}}\n",
        encoding="utf-8",
    )
    content = bibliography.read_bytes()
    imported = load_bibliography(
        bibliography,
        source_id="sanitized-test:course-reference",
        source_revision=f"sha256:{hashlib.sha256(content).hexdigest()}",
        source_path="candidate.bib",
        storage_class=RootStorageClass.LOCAL,
    )
    render = CandidateBibliographyRenderer().render(
        request=CandidateBibliographyRenderRequest(
            source=CandidateBibliographyExportRequest(
                sources=(
                    CandidateBibliographySourceDeclaration(
                        collection_id="course-reference-test",
                        observations=imported.observations,
                    ),
                )
            )
        )
    )
    entry = render.entries[0]
    fields = dict(entry.normalized_fields)
    candidate = ReferenceCandidate.create(
        proposed_citekey=entry.citekey,
        entry_type=entry.entry_type,
        title=fields.get("title"),
        authors=(fields["author"],),
        year=fields.get("year"),
        source_observation_ids=entry.source_observation_ids,
        generator=imported.candidates[0].generator,
    )
    binding = RenderedEntryCandidateBinding(
        reference_locator=entry.entry_id,
        rendered_entry_id=entry.entry_id,
        candidate_id=candidate.candidate_id,
        source_observation_ids=entry.source_observation_ids,
    )
    locator = CourseReferenceLocatorBinding(
        ordinal=1,
        display_citekey=entry.citekey,
        display_citekey_status=(
            CourseReferenceDisplayCitekeyStatus.PROPOSED_NONCANONICAL
        ),
        reference_locator=entry.entry_id,
    )
    manifest_id = _cid("course-authoring-manifest", "manifest")
    inventory_id = _cid("course-source-inventory", "inventory")
    selection = CourseReferenceSelection(
        course_id="dlsu.phy627m.gs1",
        manifest_id=manifest_id,
        inventory_id=inventory_id,
        ordinal=1,
        origin=CourseReferenceSelectionOrigin.DIRECTED_REFERENCE_SCOPE,
        role=CourseReferenceRole.MANUSCRIPT_BIBLIOGRAPHY,
        display_citekey=entry.citekey,
        display_citekey_status=(
            CourseReferenceDisplayCitekeyStatus.PROPOSED_NONCANONICAL
        ),
        reference_locator=entry.entry_id,
        locator_binding_id=locator.binding_id,
    )
    scope = CourseReferenceResolutionScope(
        course_id="dlsu.phy627m.gs1",
        course_title="Solid State Physics II",
        manifest_id=manifest_id,
        manifest_sha256=hashlib.sha256(b"manifest").hexdigest(),
        inventory_id=inventory_id,
        selections=(selection,),
    )
    catalog = ReferenceCatalog(
        tmp_path / "references.sqlite3",
        storage_class=RootStorageClass.LOCAL,
    )
    catalog.initialize()
    owner = _OwnerProvider(
        render=render,
        candidates=(candidate,),
        observations=imported.observations,
        bindings=(binding,),
    )
    service = CourseReferenceAuthorityService(catalog=catalog, provider=owner)
    return (
        ReferencesCourseReferenceAuthorityProvider(scope, service),
        catalog,
        owner,
        candidate,
    )


def _actor() -> ReviewActorRequest:
    return ReviewActorRequest(
        actor_id="control-curator",
        verification_record_id=_cid("actor-verification", "curator"),
        verification_method="authenticated-control-session",
    )


def test__provider__separates_identity_and_asset_cas_and_rereads_receipts(
    tmp_path: Path,
) -> None:
    provider, catalog, owner, candidate = _provider(tmp_path)
    queue = provider.queue("dlsu.phy627m.gs1")
    item = queue.items[0]

    assert item.allowed_identity_actions == (
        IdentityDisposition.ACCEPT_NEW,
        IdentityDisposition.REJECT,
        IdentityDisposition.DEFER,
    )
    identity_request = IdentityDecisionRequest(
        idempotency_key="identity-sequence-1",
        expected_queue_id=queue.queue_id,
        expected_item_revision_id=item.item_revision_id,
        disposition=IdentityDisposition.ACCEPT_NEW,
        target_state_projection_id=None,
        canonical_citekey=candidate.proposed_citekey,
        alias_citekeys=(),
        selected_record_match_ids=(),
        rationale="Accept only the exact bibliographic identity.",
        decided_at="2026-10-11T06:00:00Z",
        actor=_actor(),
    )
    identity = provider.decide_identity(
        "dlsu.phy627m.gs1",
        item.selection.selection_id,
        identity_request,
    )
    identity_retry = provider.decide_identity(
        "dlsu.phy627m.gs1",
        item.selection.selection_id,
        identity_request,
    )

    assert identity_retry == identity
    with pytest.raises(CourseReferenceAuthorityFailure) as conflict:
        provider.decide_identity(
            "dlsu.phy627m.gs1",
            item.selection.selection_id,
            identity_request.model_copy(
                update={"rationale": "Conflicting reuse of the same key."}
            ),
        )
    assert (
        conflict.value.code is CourseReferenceFailureCode.IDEMPOTENCY_CONFLICT
    )
    with pytest.raises(CourseReferenceAuthorityFailure) as stale_identity:
        provider.decide_identity(
            "dlsu.phy627m.gs1",
            item.selection.selection_id,
            identity_request.model_copy(
                update={"idempotency_key": "identity-stale-1"}
            ),
        )
    assert (
        stale_identity.value.code is CourseReferenceFailureCode.REVISION_STALE
    )
    assert identity.dimension == "reference-identity"
    assert identity.disposition == "ACCEPT_NEW"
    assert identity.state_projection_id is not None
    assert identity.refreshed_item.active_authority is not None
    assert identity.refreshed_item.active_authority.source_asset_id is None

    raw_asset = SourceAssetRecord(
        candidate_id=candidate.candidate_id,
        proposed_citekey=candidate.proposed_citekey,
        identity_status=candidate.lifecycle_status,
        citekey_status=candidate.citekey_status,
        sha256="a" * 64,
        byte_size=42,
        root_alias="private-library",
        relative_path="opaque.pdf",
        rights_status="rights-not-assessed",
        asset_status="managed-private-integrity-validated-source",
    )
    catalog.record_source_asset(raw_asset)
    owner.assets = (
        ReferenceAssetAuthorityEvidence.from_asset(
            raw_asset,
            runtime_availability=RuntimeAssetAvailability.AVAILABLE,
            runtime_evidence_id=_cid("runtime-asset-evidence", "available"),
        ),
    )
    asset_queue = provider.queue("dlsu.phy627m.gs1")
    asset_item = asset_queue.items[0]
    assert asset_item.asset_plan_id is not None
    assert asset_item.active_authority is not None
    assert asset_item.allowed_asset_actions[0] is AssetDisposition.AUTHORIZE

    asset_request = AssetDecisionRequest(
        idempotency_key="asset-sequence-1",
        expected_queue_id=asset_queue.queue_id,
        expected_item_revision_id=asset_item.item_revision_id,
        expected_identity_state_projection_id=(
            asset_item.active_authority.state_projection_id
        ),
        expected_asset_plan_id=asset_item.asset_plan_id,
        disposition=AssetDisposition.AUTHORIZE,
        competitors=(
            AssetCompetitorDecisionRequest(
                asset_observation_id=(
                    asset_item.assets[0].asset_observation_id
                ),
                disposition=AssetDisposition.AUTHORIZE,
                rationale="Select this exact available source asset.",
            ),
        ),
        rationale="Authorize bytes separately from work identity.",
        decided_at="2026-10-11T06:01:00Z",
        actor=_actor(),
    )
    asset = provider.decide_asset(
        "dlsu.phy627m.gs1",
        asset_item.selection.selection_id,
        asset_request,
    )
    asset_retry = provider.decide_asset(
        "dlsu.phy627m.gs1",
        asset_item.selection.selection_id,
        asset_request,
    )

    assert asset_retry == asset
    with pytest.raises(CourseReferenceAuthorityFailure) as stale_asset:
        provider.decide_asset(
            "dlsu.phy627m.gs1",
            asset_item.selection.selection_id,
            asset_request.model_copy(
                update={"idempotency_key": "asset-stale-1"}
            ),
        )
    assert stale_asset.value.code is CourseReferenceFailureCode.REVISION_STALE
    assert asset.dimension == "canonical-asset"
    assert asset.disposition == "AUTHORIZE"
    assert asset.refreshed_item.active_authority is not None
    assert asset.refreshed_item.active_authority.source_asset_id is not None
    assert catalog.counts()["human_review_decisions"] == 2


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
    )
    provider = open_references_course_reference_authority_provider(
        scope=composition.scope,
        configuration=composition.runtime,
    )
    projection = provider.queue(scope.course_id)

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


def test__provider__maps_owner_atomic_asset_race_to_concurrent_decision(
    tmp_path: Path,
) -> None:
    provider, catalog, owner, candidate = _provider(tmp_path)
    queue = provider.queue("dlsu.phy627m.gs1")
    item = queue.items[0]
    catalog.import_candidates(owner.candidates, owner.observations)
    raw_asset = SourceAssetRecord(
        candidate_id=candidate.candidate_id,
        proposed_citekey=candidate.proposed_citekey,
        identity_status=candidate.lifecycle_status,
        citekey_status=candidate.citekey_status,
        sha256="b" * 64,
        byte_size=1,
        root_alias="private-library",
        relative_path="changed.pdf",
        rights_status="rights-not-assessed",
        asset_status="observed-source-copy",
    )
    catalog.record_source_asset(raw_asset)

    with pytest.raises(CourseReferenceAuthorityFailure) as captured:
        provider.decide_identity(
            "dlsu.phy627m.gs1",
            item.selection.selection_id,
            IdentityDecisionRequest(
                idempotency_key="identity-race-1",
                expected_queue_id=queue.queue_id,
                expected_item_revision_id=item.item_revision_id,
                disposition=IdentityDisposition.ACCEPT_NEW,
                target_state_projection_id=None,
                canonical_citekey=candidate.proposed_citekey,
                alias_citekeys=(),
                selected_record_match_ids=(),
                rationale="This request used an obsolete queue.",
                decided_at="2026-10-11T06:00:00Z",
                actor=_actor(),
            ),
        )

    assert captured.value.code is (
        CourseReferenceFailureCode.CONCURRENT_DECISION
    )
    assert catalog.counts()["human_review_decisions"] == 0
