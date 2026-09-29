from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.equation_review.boundary import (
    EquationRegionResource,
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewNoncanonicalLatex,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewQueueIncomplete,
    EquationReviewQueueMalformed,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review.models import (
    DeterministicEquationEvidenceResponse,
    EquationDisplayMode,
    EquationRegionEvidenceResponse,
    EquationRenderConfirmation,
    EquationReviewCandidateResponse,
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
    EquationReviewQueueResponse,
    EquationReviewStatus,
    EquationSourceIdentityResponse,
    ProposedEquationAssistanceResponse,
    UnassistedEquationProposalResponse,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EQUATION_REVIEW_QUEUE_CONTRACT_ID as OWNER_QUEUE_CONTRACT_ID,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EQUATION_REVIEW_QUEUE_SCHEMA_VERSION as OWNER_QUEUE_SCHEMA_VERSION,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EQUATION_REVIEW_SCHEMA_VERSION as OWNER_EQUATION_REVIEW_SCHEMA_VERSION,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    HUMAN_EQUATION_REVISION_SCHEMA_VERSION as OWNER_HUMAN_SCHEMA_VERSION,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    MAX_EQUATION_REVIEW_QUEUE_CANDIDATES as OWNER_MAX_QUEUE_CANDIDATES,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationDisplayMode as OwnerDisplayMode,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationRenderConfirmation as OwnerRenderConfirmation,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewConcurrencyError as OwnerConcurrencyError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewDisposition as OwnerDisposition,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewError as OwnerReviewError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewEvidenceBinding as OwnerEvidenceBinding,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewEvidenceMismatch as OwnerEvidenceMismatch,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewPublicationError as OwnerPublicationError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueAssistanceStatus as OwnerAssistanceStatus,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueError as OwnerQueueError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueIncompleteError as OwnerQueueIncompleteError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueItem as OwnerQueueItem,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueLatestDecision as OwnerQueueDecision,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueMalformedError as OwnerQueueMalformedError,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewQueueProjection as OwnerQueueProjection,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EquationReviewStaleRevision as OwnerStaleRevision,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    HumanEquationRevision,
    HumanEquationRevisionAppendResult,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    project_equation_review_queue,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass

_MAX_REGION_BYTES = 20_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECORDED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationsEquationReviewOwner:
    """Adapt applications queue, region, and schema-3 append seams."""

    def __init__(
        self,
        document_root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._document_root = document_root.expanduser()
        self._clock = clock

    def queue(self) -> EquationReviewQueueResponse:
        _require_owner_schema()
        try:
            projection = project_equation_review_queue(
                document_root=self._root()
            )
        except OwnerQueueIncompleteError as error:
            raise EquationReviewQueueIncomplete from error
        except OwnerQueueMalformedError as error:
            raise EquationReviewQueueMalformed from error
        except OwnerQueueError as error:
            raise EquationReviewQueueMalformed from error
        except EquationReviewOwnerUnavailable:
            raise
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        try:
            return _queue_response(projection)
        except Exception as error:
            raise EquationReviewQueueMalformed from error

    def region(
        self,
        candidate_id: str,
        expected_sha256: str,
    ) -> EquationRegionResource:
        if _SHA256.fullmatch(expected_sha256) is None:
            raise EquationReviewQueueMalformed
        try:
            key = _candidate_key(candidate_id)
            relative = (
                PurePosixPath("content/equations/regions")
                / key
                / "source/image.png"
            )
            body = self._root().read_bytes(
                relative,
                max_bytes=_MAX_REGION_BYTES,
            )
        except EquationReviewOwnerUnavailable:
            raise
        except FileNotFoundError as error:
            raise EquationReviewQueueIncomplete from error
        except (OSError, ValueError) as error:
            raise EquationReviewQueueMalformed from error
        if (
            not body
            or len(body) > _MAX_REGION_BYTES
            or not body.startswith(b"\x89PNG\r\n\x1a\n")
            or hashlib.sha256(body).hexdigest() != expected_sha256
        ):
            raise EquationReviewQueueMalformed
        return EquationRegionResource(body=body, media_type="image/png")

    def append(
        self,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse:
        _require_owner_schema()
        recorded_at_utc = self._clock()
        if not isinstance(
            recorded_at_utc, datetime
        ) or recorded_at_utc.utcoffset() != timedelta(0):
            raise EquationReviewOwnerUnavailable
        try:
            owner_request = _owner_request(
                binding,
                request,
                recorded_at_utc=recorded_at_utc,
            )
            result = append_human_equation_revision(
                owner_request,
                document_root=self._root(),
            )
        except (
            EquationReviewEditAfterRender,
            EquationReviewNoncanonicalLatex,
            EquationReviewRenderStale,
        ):
            raise
        except OwnerEvidenceMismatch as error:
            raise EquationReviewEvidenceStale from error
        except OwnerStaleRevision as error:
            raise EquationReviewRevisionStale from error
        except OwnerConcurrencyError as error:
            raise EquationReviewConcurrentDecision from error
        except OwnerPublicationError as error:
            raise EquationReviewPartialOutput from error
        except OwnerReviewError as error:
            raise EquationReviewOwnerUnavailable from error
        except EquationReviewOwnerUnavailable:
            raise
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        try:
            if not isinstance(result, HumanEquationRevisionAppendResult):
                raise TypeError("owner result type is invalid")
            decision = _decision_from_revision(
                result.revision,
                expected_binding=owner_request.binding,
            )
            return EquationReviewDecisionResponse(
                candidate_id=OpaqueId(binding.candidate_id),
                **decision.model_dump(),
            )
        except Exception as error:
            raise EquationReviewPartialOutput from error

    def _root(self) -> AuthorizedRoot:
        try:
            return AuthorizedRoot.existing(
                self._document_root,
                label="pizzi2020 equation-review document",
                root_alias="equation-review-pizzi2020",
                storage_class=RootStorageClass.LOCAL,
            )
        except (OSError, ValueError) as error:
            raise EquationReviewOwnerUnavailable from error


def _require_owner_schema() -> None:
    if (
        OWNER_EQUATION_REVIEW_SCHEMA_VERSION != 3
        or OWNER_HUMAN_SCHEMA_VERSION != 3
        or OWNER_QUEUE_SCHEMA_VERSION != 1
        or OWNER_MAX_QUEUE_CANDIDATES != 256
        or OWNER_QUEUE_CONTRACT_ID
        != "projectkoios.applications.pdf-corpus-equation-review-queue"
    ):
        raise EquationReviewOwnerUnavailable


def _queue_response(projection: object) -> EquationReviewQueueResponse:
    if not isinstance(projection, OwnerQueueProjection):
        raise TypeError("owner queue projection type is invalid")
    items = tuple(_queue_item(item) for item in projection.items)
    decided = sum(item.decision is not None for item in items)
    return EquationReviewQueueResponse(
        contract_id=OpaqueId(projection.contract_id),
        schema_version=cast(Literal[1], projection.schema_version),
        projection_id=OpaqueId(projection.projection_id),
        package_id=OpaqueId(projection.package_id),
        document_id=OpaqueId(projection.document_id),
        source_sha256=projection.source_sha256,
        total=len(items),
        decided=decided,
        pending=len(items) - decided,
        items=items,
    )


def _queue_item(item: object) -> EquationReviewCandidateResponse:
    if not isinstance(item, OwnerQueueItem):
        raise TypeError("owner queue item type is invalid")
    x0, y0, x1, y1 = item.bounding_box
    decision = (
        None
        if item.latest_decision is None
        else _decision_from_queue(item.latest_decision)
    )
    expected_status = (
        EquationReviewStatus.UNREVIEWED if decision is None else decision.status
    )
    expected_owner_status = (
        "NOT_REVIEWED"
        if decision is None
        else {
            EquationReviewStatus.LEGACY_ACCEPTANCE: "ACCEPTED",
            EquationReviewStatus.ACCEPTED: "ACCEPTED",
            EquationReviewStatus.REJECTED: "REJECTED",
            EquationReviewStatus.REVISION_REQUIRED: "REVISION_REQUIRED",
        }[decision.status]
    )
    if item.decision_status.value != expected_owner_status:
        raise ValueError("owner queue decision state is inconsistent")
    return EquationReviewCandidateResponse(
        candidate_id=OpaqueId(item.candidate_id),
        source=EquationSourceIdentityResponse(
            document_id=OpaqueId(item.document_id),
            source_sha256=item.source_sha256,
            page_index=item.page_index,
            physical_page=item.physical_page_number,
            printed_page_label=item.printed_page_label,
        ),
        region=EquationRegionEvidenceResponse(
            coordinate_space="PDF_POINTS",
            x=x0,
            y=y0,
            width=x1 - x0,
            height=y1 - y0,
            image_sha256=item.region_image_sha256,
        ),
        deterministic_evidence=DeterministicEquationEvidenceResponse(
            evidence_sha256=item.candidate_evidence_sha256,
            candidate_sha256=item.native_evidence.candidate_sha256,
            raw_text=item.native_evidence.raw_text,
            source_label=item.native_evidence.source_label,
            confidence=item.native_evidence.confidence,
            evidence_status=item.native_evidence.evidence_status,
            source_block_id=item.native_evidence.source_block_id,
            detection_input_id=item.native_evidence.detection_input_id,
            warning_ids=item.native_evidence.warning_ids,
            processor_name=item.native_evidence.processor_name,
            processor_version=item.native_evidence.processor_version,
            configuration_digest=item.native_evidence.configuration_digest,
        ),
        display_mode=EquationDisplayMode(item.display_mode),
        assistance=_assistance(item),
        status=expected_status,
        current_revision=0 if decision is None else decision.revision,
        expected_previous_revision=0 if decision is None else decision.revision,
        decision=decision,
    )


def _assistance(
    item: OwnerQueueItem,
) -> UnassistedEquationProposalResponse | ProposedEquationAssistanceResponse:
    assistance = item.assistance
    if assistance.status is OwnerAssistanceStatus.NOT_STARTED:
        if any(
            value is not None
            for value in (
                assistance.attempt_id,
                assistance.method,
                assistance.proposal,
                assistance.proposal_sha256,
            )
        ):
            raise ValueError("unassisted owner queue item is inconsistent")
        return UnassistedEquationProposalResponse(
            status="NOT_STARTED",
            attempt_id=None,
            method=None,
            proposal_sha256=None,
            proposed_latex=None,
        )
    if assistance.status is not OwnerAssistanceStatus.AUTOMATED_UNREVIEWED:
        raise ValueError("owner assistance status is invalid")
    if any(
        value is None
        for value in (
            assistance.attempt_id,
            assistance.method,
            assistance.proposal,
            assistance.proposal_sha256,
        )
    ):
        raise ValueError("assisted owner queue item is incomplete")
    assert assistance.attempt_id is not None
    assert assistance.method is not None
    assert assistance.proposal is not None
    assert assistance.proposal_sha256 is not None
    return ProposedEquationAssistanceResponse(
        status="AUTOMATED_UNREVIEWED",
        attempt_id=OpaqueId(assistance.attempt_id),
        method=assistance.method,
        proposal_sha256=assistance.proposal_sha256,
        proposed_latex=assistance.proposal,
    )


def _decision_from_queue(value: object) -> EquationReviewDecision:
    if not isinstance(value, OwnerQueueDecision):
        raise TypeError("owner queue decision type is invalid")
    render_values = (
        value.renderer_id,
        value.renderer_version,
        value.rendered_reviewer_latex_sha256,
        value.rendered_obsidian_markdown_sha256,
    )
    render = None
    if any(item is not None for item in render_values):
        if any(item is None for item in render_values):
            raise ValueError("owner render provenance is incomplete")
        assert value.renderer_id is not None
        assert value.renderer_version is not None
        assert value.rendered_reviewer_latex_sha256 is not None
        assert value.rendered_obsidian_markdown_sha256 is not None
        render = EquationRenderConfirmation(
            renderer_id=value.renderer_id,
            renderer_version=value.renderer_version,
            rendered_reviewer_latex_sha256=(
                value.rendered_reviewer_latex_sha256
            ),
            rendered_obsidian_markdown_sha256=(
                value.rendered_obsidian_markdown_sha256
            ),
        )
    disposition = EquationReviewDisposition(value.disposition.value)
    return EquationReviewDecision(
        status=_queue_status(value),
        schema_version=cast(Literal[2, 3], value.schema_version),
        disposition=disposition,
        assistance_proposal_sha256=value.assistance_proposal_sha256,
        reviewer_latex=value.reviewer_latex,
        reviewer_latex_sha256=value.reviewer_latex_sha256,
        obsidian_markdown=value.obsidian_markdown,
        obsidian_markdown_sha256=value.obsidian_markdown_sha256,
        display_mode=(
            None
            if value.display_mode is None
            else EquationDisplayMode(value.display_mode)
        ),
        render_confirmation=render,
        note=value.note,
        revision=value.revision,
        revision_id=OpaqueId(value.revision_id),
        recorded_at_utc=_recorded_at(value.recorded_at_utc),
    )


def _queue_status(value: OwnerQueueDecision) -> EquationReviewStatus:
    if value.disposition is OwnerDisposition.ACCEPT_TRANSCRIPTION:
        if value.status.value != "ACCEPTED":
            raise ValueError("owner queue acceptance status is inconsistent")
        if value.schema_version == 2:
            return EquationReviewStatus.LEGACY_ACCEPTANCE
        return EquationReviewStatus.ACCEPTED
    if value.disposition is OwnerDisposition.REJECT_CANDIDATE:
        if value.status.value != "REJECTED":
            raise ValueError("owner queue rejection status is inconsistent")
        return EquationReviewStatus.REJECTED
    if value.status.value != "REVISION_REQUIRED":
        raise ValueError("owner queue revision status is inconsistent")
    return EquationReviewStatus.REVISION_REQUIRED


def _recorded_at(value: str) -> datetime:
    if _RECORDED_AT.fullmatch(value) is None:
        raise ValueError("owner queue timestamp is malformed")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("owner queue timestamp is not UTC")
    return parsed


def _candidate_key(candidate_id: str) -> str:
    valid = OpaqueId(candidate_id)
    stable_prefix = "equation-candidate:sha256:"
    if valid.startswith(stable_prefix):
        digest = valid.removeprefix(stable_prefix)
        if _SHA256.fullmatch(digest) is None:
            raise ValueError("candidate identity digest is malformed")
        return digest
    return hashlib.sha256(valid.encode("utf-8")).hexdigest()


def _owner_binding(
    binding: EquationReviewEvidenceBinding,
) -> OwnerEvidenceBinding:
    try:
        return OwnerEvidenceBinding(
            document_id=binding.document_id,
            candidate_id=binding.candidate_id,
            source_sha256=binding.source_sha256,
            candidate_evidence_sha256=binding.candidate_evidence_sha256,
            region_image_sha256=binding.region_image_sha256,
        )
    except (TypeError, OwnerReviewError) as error:
        raise EquationReviewOwnerUnavailable from error


def _owner_request(
    binding: EquationReviewEvidenceBinding,
    request: EquationReviewDecisionRequest,
    *,
    recorded_at_utc: datetime,
) -> HumanEquationRevisionRequest:
    owner_display_mode: OwnerDisplayMode | None = None
    owner_confirmation: OwnerRenderConfirmation | None = None
    if request.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION:
        reviewer_latex = request.reviewer_latex
        display_mode = request.display_mode
        confirmation = request.render_confirmation
        if (
            reviewer_latex is None
            or display_mode is None
            or confirmation is None
        ):
            raise EquationReviewOwnerUnavailable
        owner_display_mode = OwnerDisplayMode(display_mode.value)
        try:
            expected = OwnerRenderConfirmation.create(
                renderer_id=confirmation.renderer_id,
                renderer_version=confirmation.renderer_version,
                reviewer_latex=reviewer_latex,
                display_mode=owner_display_mode,
            )
        except OwnerReviewError as error:
            raise EquationReviewNoncanonicalLatex from error
        if (
            confirmation.rendered_reviewer_latex_sha256
            != expected.rendered_reviewer_latex_sha256
        ):
            raise EquationReviewEditAfterRender
        if (
            confirmation.rendered_obsidian_markdown_sha256
            != expected.rendered_obsidian_markdown_sha256
        ):
            raise EquationReviewRenderStale
        owner_confirmation = OwnerRenderConfirmation(
            renderer_id=confirmation.renderer_id,
            renderer_version=confirmation.renderer_version,
            rendered_reviewer_latex_sha256=(
                confirmation.rendered_reviewer_latex_sha256
            ),
            rendered_obsidian_markdown_sha256=(
                confirmation.rendered_obsidian_markdown_sha256
            ),
        )
    return HumanEquationRevisionRequest(
        binding=_owner_binding(binding),
        disposition=OwnerDisposition(request.disposition.value),
        assistance_proposal_sha256=request.assistance_proposal_sha256,
        reviewer_latex=request.reviewer_latex,
        display_mode=owner_display_mode,
        render_confirmation=owner_confirmation,
        note=request.note,
        recorded_at_utc=recorded_at_utc,
        expected_previous_revision=request.expected_previous_revision,
    )


def _decision_from_revision(
    revision: object,
    *,
    expected_binding: OwnerEvidenceBinding,
) -> EquationReviewDecision:
    validated = _validated_owner_revision(
        revision,
        expected_binding=expected_binding,
    )
    render_confirmation = validated.render_confirmation
    return EquationReviewDecision(
        status=_revision_status(validated),
        schema_version=cast(Literal[2, 3], validated.schema_version),
        disposition=EquationReviewDisposition(validated.disposition.value),
        assistance_proposal_sha256=validated.assistance_proposal_sha256,
        reviewer_latex=validated.reviewer_latex,
        reviewer_latex_sha256=validated.reviewer_latex_sha256,
        obsidian_markdown=validated.obsidian_markdown,
        obsidian_markdown_sha256=validated.obsidian_markdown_sha256,
        display_mode=(
            None
            if validated.display_mode is None
            else EquationDisplayMode(validated.display_mode.value)
        ),
        render_confirmation=(
            None
            if render_confirmation is None
            else EquationRenderConfirmation(
                renderer_id=render_confirmation.renderer_id,
                renderer_version=render_confirmation.renderer_version,
                rendered_reviewer_latex_sha256=(
                    render_confirmation.rendered_reviewer_latex_sha256
                ),
                rendered_obsidian_markdown_sha256=(
                    render_confirmation.rendered_obsidian_markdown_sha256
                ),
            )
        ),
        note=validated.note,
        revision=validated.revision,
        revision_id=OpaqueId(validated.revision_id),
        recorded_at_utc=validated.recorded_at_utc,
    )


def _validated_owner_revision(
    revision: object,
    *,
    expected_binding: OwnerEvidenceBinding,
) -> HumanEquationRevision:
    if not isinstance(revision, HumanEquationRevision):
        raise TypeError("owner revision type is invalid")
    binding = OwnerEvidenceBinding(
        document_id=revision.binding.document_id,
        candidate_id=revision.binding.candidate_id,
        source_sha256=revision.binding.source_sha256,
        candidate_evidence_sha256=revision.binding.candidate_evidence_sha256,
        region_image_sha256=revision.binding.region_image_sha256,
    )
    if binding != expected_binding:
        raise ValueError("owner revision binding is inconsistent")
    confirmation = revision.render_confirmation
    validated_confirmation = (
        None
        if confirmation is None
        else OwnerRenderConfirmation(
            renderer_id=confirmation.renderer_id,
            renderer_version=confirmation.renderer_version,
            rendered_reviewer_latex_sha256=(
                confirmation.rendered_reviewer_latex_sha256
            ),
            rendered_obsidian_markdown_sha256=(
                confirmation.rendered_obsidian_markdown_sha256
            ),
        )
    )
    return HumanEquationRevision(
        binding=binding,
        disposition=revision.disposition,
        assistance_proposal_sha256=revision.assistance_proposal_sha256,
        reviewer_latex=revision.reviewer_latex,
        reviewer_latex_sha256=revision.reviewer_latex_sha256,
        obsidian_markdown=revision.obsidian_markdown,
        obsidian_markdown_sha256=revision.obsidian_markdown_sha256,
        display_mode=revision.display_mode,
        render_confirmation=validated_confirmation,
        note=revision.note,
        revision=revision.revision,
        recorded_at_utc=revision.recorded_at_utc,
        revision_id=revision.revision_id,
        schema_version=revision.schema_version,
    )


def _revision_status(revision: HumanEquationRevision) -> EquationReviewStatus:
    if revision.disposition is OwnerDisposition.ACCEPT_TRANSCRIPTION:
        if revision.schema_version == 2:
            return EquationReviewStatus.LEGACY_ACCEPTANCE
        return EquationReviewStatus.ACCEPTED
    if revision.disposition is OwnerDisposition.REJECT_CANDIDATE:
        return EquationReviewStatus.REJECTED
    return EquationReviewStatus.REVISION_REQUIRED
