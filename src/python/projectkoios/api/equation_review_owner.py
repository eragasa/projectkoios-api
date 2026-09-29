from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.equation_review_boundary import (
    EquationReviewConcurrentDecision,
    EquationReviewEditAfterRender,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewNoncanonicalLatex,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewRenderStale,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review_models import (
    EquationDisplayMode,
    EquationRenderConfirmation,
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
    EquationReviewStatus,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EQUATION_REVIEW_SCHEMA_VERSION as OWNER_EQUATION_REVIEW_SCHEMA_VERSION,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    HUMAN_EQUATION_REVISION_SCHEMA_VERSION as OWNER_HUMAN_SCHEMA_VERSION,
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
    EquationReviewStaleRevision as OwnerStaleRevision,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    HumanEquationRevision,
    HumanEquationRevisionAppendResult,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    load_latest_human_equation_revision,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass
from pydantic import ValidationError


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationsEquationReviewDecisionStore:
    """Narrow adapter over the applications-owned schema-3 append seam."""

    def __init__(
        self,
        document_root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._document_root = document_root.expanduser()
        self._clock = clock

    def latest(
        self,
        binding: EquationReviewEvidenceBinding,
    ) -> EquationReviewDecision | None:
        _require_owner_schema()
        owner_binding = _owner_binding(binding)
        root = self._root()
        try:
            revision = load_latest_human_equation_revision(
                owner_binding,
                document_root=root,
            )
        except OwnerEvidenceMismatch as error:
            raise EquationReviewEvidenceStale from error
        except OwnerPublicationError as error:
            raise EquationReviewPartialOutput from error
        except OwnerReviewError as error:
            raise EquationReviewOwnerUnavailable from error
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        if revision is None:
            return None
        try:
            return _decision(revision, expected_binding=owner_binding)
        except (
            AttributeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            raise EquationReviewPartialOutput from error

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
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        try:
            if not isinstance(result, HumanEquationRevisionAppendResult):
                raise TypeError("owner result type is invalid")
            decision = _decision(
                result.revision,
                expected_binding=owner_request.binding,
            )
            return EquationReviewDecisionResponse(
                candidate_id=OpaqueId(binding.candidate_id),
                **decision.model_dump(),
            )
        except (
            AttributeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
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
    ):
        raise EquationReviewOwnerUnavailable


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


def _decision(
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
        status=_status(validated),
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


def _status(revision: HumanEquationRevision) -> EquationReviewStatus:
    if revision.disposition is OwnerDisposition.ACCEPT_TRANSCRIPTION:
        if revision.schema_version == 2:
            return EquationReviewStatus.LEGACY_ACCEPTANCE
        return EquationReviewStatus.ACCEPTED
    if revision.disposition is OwnerDisposition.REJECT_CANDIDATE:
        return EquationReviewStatus.REJECTED
    return EquationReviewStatus.REVISION_REQUIRED
