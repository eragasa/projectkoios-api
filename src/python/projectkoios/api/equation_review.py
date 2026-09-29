from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.config import (
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
)
from projectkoios.api.equation_review_models import (
    MAX_EQUATION_REVIEW_CANDIDATES,
    EquationReviewCandidateResponse,
    EquationReviewDecision,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
    EquationReviewQueueResponse,
    ProposedEquationAssistanceResponse,
)
from projectkoios.api.equation_review_owner import (
    ApplicationsEquationReviewDecisionStore,
    EquationReviewDecisionStore,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceStale,
    EquationReviewOwnerUnavailable,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

_MAX_BUNDLE_BYTES = 20_000_000
MAX_EQUATION_REGION_BYTES = 20_000_000
QUEUE_OWNER_PROJECTION_BUDGET_SECONDS = 2.0
_PIZZI2020 = "pizzi2020"


class EquationReviewUnavailable(RuntimeError):
    """Configured equation-review evidence is absent or invalid."""


class EquationReviewNotFound(LookupError):
    """No configured equation-review projection has the opaque identity."""


class InvalidEquationReviewDecision(ValueError):
    """A requested decision is not bound to the displayed candidate."""


@dataclass(frozen=True)
class EquationRegionResource:
    body: bytes
    media_type: str


class _EquationReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1"]
    document_id: Literal["pizzi2020"]
    items: tuple[EquationReviewCandidateResponse, ...] = Field(
        max_length=MAX_EQUATION_REVIEW_CANDIDATES
    )

    @model_validator(mode="after")
    def has_only_owner_projected_unique_candidates(
        self,
    ) -> _EquationReviewBundle:
        candidate_ids = [str(item.candidate_id) for item in self.items]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("equation bundle candidate ids must be unique")
        if any(item.decision is not None for item in self.items):
            raise ValueError(
                "equation bundle cannot claim applications-owned decisions"
            )
        if any(
            item.source.document_id != self.document_id for item in self.items
        ):
            raise ValueError("equation bundle source document is inconsistent")
        return self


class EquationReviewRepository:
    """Read private projections and delegate decisions to the owner seam."""

    def __init__(
        self,
        configuration: EquationReviewConfiguration,
        *,
        decision_store: EquationReviewDecisionStore | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._configuration = configuration
        self._monotonic = monotonic
        configured = configuration.pizzi2020
        self._decision_store = (
            decision_store
            if decision_store is not None
            else (
                ApplicationsEquationReviewDecisionStore(
                    configured.document_root
                )
                if configured is not None
                else None
            )
        )

    def queue(self, document_id: str) -> EquationReviewQueueResponse:
        bundle = self._bundle(document_id)
        store = self._require_decision_store()
        deadline = self._monotonic() + QUEUE_OWNER_PROJECTION_BUDGET_SECONDS
        items: list[EquationReviewCandidateResponse] = []
        for index, candidate in enumerate(bundle.items):
            decision = _validated_latest_decision(
                candidate,
                store.latest(_binding(candidate)),
            )
            payload = candidate.model_dump(
                mode="python",
                round_trip=True,
                warnings=False,
            )
            payload["decision"] = (
                decision.model_dump(
                    mode="python",
                    round_trip=True,
                    warnings=False,
                )
                if decision is not None
                else None
            )
            try:
                items.append(
                    EquationReviewCandidateResponse.model_validate(
                        payload,
                        strict=True,
                    )
                )
            except ValidationError as error:
                raise EquationReviewOwnerUnavailable from error
            if index + 1 < len(bundle.items) and self._monotonic() > deadline:
                raise EquationReviewOwnerUnavailable
        return EquationReviewQueueResponse(
            document_id=OpaqueId(bundle.document_id),
            total=len(items),
            decided=sum(item.decision is not None for item in items),
            items=tuple(items),
        )

    def region(self, candidate_id: str) -> EquationRegionResource:
        candidate = self._candidate(candidate_id)
        configuration = self._require_pizzi2020_configuration()
        root = configuration.regions_root.expanduser()
        if root.is_symlink():
            raise EquationReviewUnavailable
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as error:
            raise EquationReviewUnavailable from error
        if not resolved_root.is_dir():
            raise EquationReviewUnavailable

        expected_hash = candidate.region.image_sha256
        path = resolved_root / expected_hash
        if path.is_symlink():
            raise EquationReviewUnavailable
        try:
            stat = path.stat()
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise EquationReviewUnavailable from error
        if (
            resolved.parent != resolved_root
            or not resolved.is_file()
            or stat.st_size < 1
            or stat.st_size > MAX_EQUATION_REGION_BYTES
        ):
            raise EquationReviewUnavailable
        try:
            body = resolved.read_bytes()
        except OSError as error:
            raise EquationReviewUnavailable from error
        if (
            not body
            or len(body) > MAX_EQUATION_REGION_BYTES
            or hashlib.sha256(body).hexdigest() != expected_hash
        ):
            raise EquationReviewUnavailable
        media_type = _image_media_type(body)
        if media_type is None:
            raise EquationReviewUnavailable
        return EquationRegionResource(body=body, media_type=media_type)

    def decide(
        self,
        candidate_id: str,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse:
        binding = self.decision_binding(candidate_id, request)
        response = self._require_decision_store().append(binding, request)
        try:
            validated = EquationReviewDecisionResponse.model_validate(
                response.model_dump(
                    mode="python",
                    round_trip=True,
                    warnings=False,
                ),
                strict=True,
            )
        except (AttributeError, ValidationError) as error:
            raise EquationReviewOwnerUnavailable from error
        if (
            validated.candidate_id != binding.candidate_id
            or validated.disposition is not request.disposition
            or validated.assistance_proposal_sha256
            != request.assistance_proposal_sha256
            or validated.note != request.note
        ):
            raise EquationReviewOwnerUnavailable
        return validated

    def decision_binding(
        self,
        candidate_id: str,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewEvidenceBinding:
        candidate = self._candidate(candidate_id)
        assistance = candidate.assistance
        request_hash = request.assistance_proposal_sha256
        if request_hash is not None and (
            not isinstance(assistance, ProposedEquationAssistanceResponse)
            or assistance.proposal_sha256 != request_hash
        ):
            raise InvalidEquationReviewDecision
        if (
            request.disposition
            is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
            and not isinstance(
                assistance,
                ProposedEquationAssistanceResponse,
            )
        ):
            raise InvalidEquationReviewDecision
        return _binding(candidate)

    def _candidate(self, candidate_id: str) -> EquationReviewCandidateResponse:
        bundle = self._bundle(_PIZZI2020)
        for candidate in bundle.items:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise EquationReviewNotFound(candidate_id)

    def _bundle(self, document_id: str) -> _EquationReviewBundle:
        if document_id != _PIZZI2020:
            raise EquationReviewNotFound(document_id)
        configuration = self._require_pizzi2020_configuration()
        path = configuration.bundle_path.expanduser()
        if path.is_symlink():
            raise EquationReviewUnavailable
        try:
            stat = path.stat()
        except OSError as error:
            raise EquationReviewUnavailable from error
        if (
            not path.is_file()
            or stat.st_size < 1
            or stat.st_size > _MAX_BUNDLE_BYTES
        ):
            raise EquationReviewUnavailable
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise EquationReviewUnavailable from error
        if not payload or len(payload) > _MAX_BUNDLE_BYTES:
            raise EquationReviewUnavailable
        try:
            return _EquationReviewBundle.model_validate_json(
                payload,
                strict=True,
            )
        except ValidationError as error:
            raise EquationReviewUnavailable from error

    def _require_pizzi2020_configuration(
        self,
    ) -> EquationReviewDocumentConfiguration:
        configuration = self._configuration.pizzi2020
        if configuration is None:
            raise EquationReviewUnavailable
        return configuration

    def _require_decision_store(self) -> EquationReviewDecisionStore:
        if self._decision_store is None:
            raise EquationReviewOwnerUnavailable
        return self._decision_store


def _binding(
    candidate: EquationReviewCandidateResponse,
) -> EquationReviewEvidenceBinding:
    return EquationReviewEvidenceBinding(
        document_id=str(candidate.source.document_id),
        candidate_id=str(candidate.candidate_id),
        source_sha256=candidate.source.source_sha256,
        candidate_evidence_sha256=(
            candidate.deterministic_evidence.evidence_sha256
        ),
        region_image_sha256=candidate.region.image_sha256,
    )


def _validated_latest_decision(
    candidate: EquationReviewCandidateResponse,
    decision: EquationReviewDecision | None,
) -> EquationReviewDecision | None:
    if decision is None:
        return None
    try:
        validated = EquationReviewDecision.model_validate(
            decision.model_dump(
                mode="python",
                round_trip=True,
                warnings=False,
            ),
            strict=True,
        )
    except (AttributeError, ValidationError) as error:
        raise EquationReviewOwnerUnavailable from error
    proposal_hash = validated.assistance_proposal_sha256
    assistance = candidate.assistance
    if proposal_hash is not None and (
        not isinstance(assistance, ProposedEquationAssistanceResponse)
        or assistance.proposal_sha256 != proposal_hash
    ):
        raise EquationReviewEvidenceStale
    return validated


def _image_media_type(body: bytes) -> str | None:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(body) >= 12 and body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    return None
