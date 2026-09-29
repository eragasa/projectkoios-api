from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from projectkoios.api.equation_review_models import (
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
)


class EquationReviewOwnerFailure(RuntimeError):
    """The applications-owned equation-review seam could not complete."""


class EquationReviewEvidenceStale(EquationReviewOwnerFailure):
    """The immutable candidate evidence no longer matches."""


class EquationReviewRevisionStale(EquationReviewOwnerFailure):
    """The browser's expected previous human revision is stale."""


class EquationReviewConcurrentDecision(EquationReviewOwnerFailure):
    """A different writer won the same exclusive append position."""


class EquationReviewPartialOutput(EquationReviewOwnerFailure):
    """Applications found partial, malformed, or invalid review output."""


class EquationReviewOwnerUnavailable(EquationReviewOwnerFailure):
    """The configured applications-owned document root is unavailable."""


@dataclass(frozen=True)
class EquationReviewEvidenceBinding:
    document_id: str
    candidate_id: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str


class EquationReviewDecisionStore(Protocol):
    def latest(
        self,
        binding: EquationReviewEvidenceBinding,
    ) -> EquationReviewDecision | None: ...

    def append(
        self,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse: ...
