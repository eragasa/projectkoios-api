from __future__ import annotations

import hashlib

from projectkoios.api.config import EquationReviewConfiguration
from projectkoios.api.equation_review.boundary import (
    EquationRegionResource,
    EquationReviewEvidenceBinding,
    EquationReviewOwner,
    EquationReviewOwnerFailure,
    EquationReviewOwnerUnavailable,
    EquationReviewPartialOutput,
    EquationReviewQueueMalformed,
    EquationReviewRenderStale,
)
from projectkoios.api.equation_review.models import (
    EquationReviewCandidateResponse,
    EquationReviewDecisionRequest,
    EquationReviewDecisionResponse,
    EquationReviewDisposition,
    EquationReviewQueueResponse,
    ProposedEquationAssistanceResponse,
)

MAX_EQUATION_REGION_BYTES = 20_000_000
_PIZZI2020 = "pizzi2020"


class EquationReviewNotFound(LookupError):
    """No configured equation-review projection has the opaque identity."""


class InvalidEquationReviewDecision(ValueError):
    """A requested decision is not bound to the displayed candidate."""


class EquationReviewRepository:
    """Validate an applications-owned queue and delegate immutable writes."""

    def __init__(
        self,
        configuration: EquationReviewConfiguration,
        *,
        owner: EquationReviewOwner | None = None,
    ) -> None:
        self._configuration = configuration
        self._owner = owner

    def queue(self, document_id: str) -> EquationReviewQueueResponse:
        if document_id != _PIZZI2020:
            raise EquationReviewNotFound(document_id)
        return self._owner_queue()

    def region(self, candidate_id: str) -> EquationRegionResource:
        candidate = self._candidate(self._owner_queue(), candidate_id)
        try:
            resource = self._require_owner().region(
                candidate_id,
                candidate.region.image_sha256,
            )
        except EquationReviewOwnerFailure:
            raise
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        if (
            not isinstance(resource, EquationRegionResource)
            or not isinstance(resource.body, bytes)
            or not resource.body
            or len(resource.body) > MAX_EQUATION_REGION_BYTES
            or resource.media_type != "image/png"
            or not resource.body.startswith(b"\x89PNG\r\n\x1a\n")
            or hashlib.sha256(resource.body).hexdigest()
            != candidate.region.image_sha256
        ):
            raise EquationReviewQueueMalformed
        return resource

    def decide(
        self,
        candidate_id: str,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewDecisionResponse:
        current = self._owner_queue()
        candidate = self._candidate(current, candidate_id)
        binding = self._decision_binding(candidate, request)
        try:
            appended = self._require_owner().append(binding, request)
        except EquationReviewOwnerFailure:
            raise
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        try:
            validated_append = EquationReviewDecisionResponse.model_validate(
                appended.model_dump(
                    mode="python",
                    round_trip=True,
                    warnings=False,
                ),
                strict=True,
            )
        except Exception as error:
            raise EquationReviewPartialOutput from error
        self._validate_append_response(
            validated_append,
            binding=binding,
            request=request,
        )

        refreshed = self._owner_queue()
        refreshed_candidate = self._candidate(refreshed, candidate_id)
        decision = refreshed_candidate.decision
        if decision is None:
            raise EquationReviewPartialOutput
        refreshed_response = EquationReviewDecisionResponse(
            candidate_id=refreshed_candidate.candidate_id,
            **decision.model_dump(
                mode="python",
                round_trip=True,
                warnings=False,
            ),
        )
        if refreshed_response != validated_append:
            raise EquationReviewPartialOutput
        return refreshed_response

    def _decision_binding(
        self,
        candidate: EquationReviewCandidateResponse,
        request: EquationReviewDecisionRequest,
    ) -> EquationReviewEvidenceBinding:
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
        if (
            request.display_mode is not None
            and request.display_mode is not candidate.display_mode
        ):
            raise EquationReviewRenderStale
        return EquationReviewEvidenceBinding(
            document_id=str(candidate.source.document_id),
            candidate_id=str(candidate.candidate_id),
            source_sha256=candidate.source.source_sha256,
            candidate_evidence_sha256=(
                candidate.deterministic_evidence.evidence_sha256
            ),
            region_image_sha256=candidate.region.image_sha256,
        )

    def _owner_queue(self) -> EquationReviewQueueResponse:
        if self._configuration.pizzi2020 is None:
            raise EquationReviewOwnerUnavailable
        owner = self._require_owner()
        try:
            projected = owner.queue()
        except EquationReviewOwnerFailure:
            raise
        except Exception as error:
            raise EquationReviewOwnerUnavailable from error
        try:
            queue = EquationReviewQueueResponse.model_validate(
                projected.model_dump(
                    mode="python",
                    round_trip=True,
                    warnings=False,
                ),
                strict=True,
            )
        except Exception as error:
            raise EquationReviewQueueMalformed from error
        if queue.document_id != _PIZZI2020:
            raise EquationReviewQueueMalformed
        return queue

    def _require_owner(self) -> EquationReviewOwner:
        if self._owner is None:
            raise EquationReviewOwnerUnavailable
        return self._owner

    @staticmethod
    def _candidate(
        queue: EquationReviewQueueResponse,
        candidate_id: str,
    ) -> EquationReviewCandidateResponse:
        for candidate in queue.items:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise EquationReviewNotFound(candidate_id)

    @staticmethod
    def _validate_append_response(
        response: EquationReviewDecisionResponse,
        *,
        binding: EquationReviewEvidenceBinding,
        request: EquationReviewDecisionRequest,
    ) -> None:
        if (
            response.candidate_id != binding.candidate_id
            or response.schema_version != 3
            or response.disposition is not request.disposition
            or response.assistance_proposal_sha256
            != request.assistance_proposal_sha256
            or response.note != request.note
            or response.revision != request.expected_previous_revision + 1
        ):
            raise EquationReviewPartialOutput
        if (
            request.disposition
            is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
        ):
            if (
                response.reviewer_latex != request.reviewer_latex
                or response.display_mode is not request.display_mode
                or response.render_confirmation != request.render_confirmation
            ):
                raise EquationReviewPartialOutput
        elif any(
            value is not None
            for value in (
                response.reviewer_latex,
                response.reviewer_latex_sha256,
                response.obsidian_markdown,
                response.obsidian_markdown_sha256,
                response.display_mode,
                response.render_confirmation,
            )
        ):
            raise EquationReviewPartialOutput
