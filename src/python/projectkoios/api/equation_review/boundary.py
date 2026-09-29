from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from projectkoios.api.equation_review.models import (
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewQueueResponse,
)


class EquationReviewOwnerFailure(RuntimeError):
    """The applications-owned equation-review seam could not complete."""


class EquationReviewEvidenceStale(EquationReviewOwnerFailure):
    """The immutable candidate evidence no longer matches."""


class EquationReviewRevisionStale(EquationReviewOwnerFailure):
    """The browser's expected previous human revision is stale."""


class EquationReviewRenderStale(EquationReviewOwnerFailure):
    """The rendered canonical wrapper no longer matches the request."""


class EquationReviewEditAfterRender(EquationReviewOwnerFailure):
    """Reviewer LaTeX changed after the confirmed render."""


class EquationReviewNoncanonicalLatex(EquationReviewOwnerFailure):
    """Reviewer LaTeX is not the owner's canonical math-body form."""


class EquationReviewConcurrentDecision(EquationReviewOwnerFailure):
    """A different writer won the same exclusive append position."""


class EquationReviewPartialOutput(EquationReviewOwnerFailure):
    """Applications found partial or invalid append output."""


class EquationReviewQueueIncomplete(EquationReviewOwnerFailure):
    """The explicit completed document package is incomplete."""


class EquationReviewQueueMalformed(EquationReviewOwnerFailure):
    """The package, candidate evidence, or review tree is malformed."""


class EquationReviewOwnerUnavailable(EquationReviewOwnerFailure):
    """The configured applications-owned document root is unavailable."""


@dataclass(frozen=True)
class EquationReviewEvidenceBinding:
    document_id: str
    candidate_id: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str


@dataclass(frozen=True)
class EquationRegionResource:
    body: bytes
    media_type: str


class EquationReviewOwner(Protocol):
    def queue(self) -> EquationReviewQueueResponse: ...

    def region(
        self,
        candidate_id: str,
        expected_sha256: str,
    ) -> EquationRegionResource: ...

    def append(
        self,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse: ...
