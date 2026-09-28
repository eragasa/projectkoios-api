from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from projectkoios.api.boundary_models import OpaqueId
from projectkoios.api.config import (
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
)
from projectkoios.api.equation_review_models import (
    EquationReviewCandidateResponse,
    EquationReviewDecisionRequest,
    EquationReviewDisposition,
    EquationReviewQueueResponse,
    ProposedEquationAssistanceResponse,
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


@dataclass(frozen=True)
class EquationDecisionBinding:
    """Validated immutable evidence identities for a future owner append."""

    document_id: str
    candidate_id: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str
    assistance_proposal_sha256: str | None


class _EquationReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1"]
    document_id: Literal["pizzi2020"]
    items: tuple[EquationReviewCandidateResponse, ...] = Field(
        max_length=100_000
    )

    @model_validator(mode="after")
    def has_only_unpersisted_unique_candidates(
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
    """Read an explicitly configured, content-addressed private projection."""

    def __init__(self, configuration: EquationReviewConfiguration) -> None:
        self._configuration = configuration

    def queue(self, document_id: str) -> EquationReviewQueueResponse:
        bundle = self._bundle(document_id)
        return EquationReviewQueueResponse(
            document_id=OpaqueId(bundle.document_id),
            total=len(bundle.items),
            decided=0,
            items=bundle.items,
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

    def decision_binding(
        self,
        candidate_id: str,
        request: EquationReviewDecisionRequest,
    ) -> EquationDecisionBinding:
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
        return EquationDecisionBinding(
            document_id=str(candidate.source.document_id),
            candidate_id=str(candidate.candidate_id),
            source_sha256=candidate.source.source_sha256,
            candidate_evidence_sha256=(
                candidate.deterministic_evidence.evidence_sha256
            ),
            region_image_sha256=candidate.region.image_sha256,
            assistance_proposal_sha256=request_hash,
        )

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


def _image_media_type(body: bytes) -> str | None:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(body) >= 12 and body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    return None
