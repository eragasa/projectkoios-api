from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.equation_review_boundary import (
    EquationReviewConcurrentDecision,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewRevisionStale,
)
from projectkoios.api.equation_review_models import (
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
)
from projectkoios.applications.pdf_corpus_ingestion import (
    EQUATION_REVIEW_SCHEMA_VERSION as OWNER_EQUATION_REVIEW_SCHEMA_VERSION,
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
    """Narrow adapter over the applications-owned schema-2 append seam."""

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
            return _decision(revision)
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
            owner_request = HumanEquationRevisionRequest(
                binding=_owner_binding(binding),
                disposition=OwnerDisposition(request.disposition.value),
                assistance_proposal_sha256=(request.assistance_proposal_sha256),
                note=request.note,
                recorded_at_utc=recorded_at_utc,
                expected_previous_revision=(request.expected_previous_revision),
            )
            result = append_human_equation_revision(
                owner_request,
                document_root=self._root(),
            )
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
            decision = _decision(result.revision)
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
    if OWNER_EQUATION_REVIEW_SCHEMA_VERSION != 2:
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


def _decision(revision: object) -> EquationReviewDecision:
    if not isinstance(revision, HumanEquationRevision):
        raise TypeError("owner revision type is invalid")
    return EquationReviewDecision(
        disposition=EquationReviewDisposition(revision.disposition.value),
        assistance_proposal_sha256=revision.assistance_proposal_sha256,
        note=revision.note,
        revision=revision.revision,
        updated_at_utc=revision.recorded_at_utc,
    )
