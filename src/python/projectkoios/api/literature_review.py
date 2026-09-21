from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from projectkoios.api.literature_review_models import (
    LiteratureClaimProgressResponse,
    LiteratureClaimStatus,
    LiteratureEquationResponse,
    LiteratureEvidenceReferenceResponse,
    LiteratureReviewPhase,
    LiteratureReviewProgressResponse,
    LiteratureStatusCountResponse,
    LiteratureValidationFrameResponse,
    ProvidedReferenceListResponse,
    ProvidedReferenceResponse,
    ProvidedReferenceStatus,
)
from projectkoios.references import (
    InvalidProvidedReference as ReferenceIntakeInvalid,
)
from projectkoios.references import (
    ProvidedReference as IntakeProvidedReference,
)
from projectkoios.references import (
    ProvidedReferenceIntakeError,
    ProvidedReferenceIntakeStore,
)

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILE_BYTES = 1_000_000


class LiteratureReviewUnavailable(RuntimeError):
    pass


class InvalidProvidedReference(ValueError):
    pass


@dataclass(frozen=True)
class _Claim:
    claim_id: str
    section: str
    claim: str


class LiteratureReviewRepository:
    def __init__(self, run_path: Path | None) -> None:
        self.run_path = run_path

    def progress(self) -> LiteratureReviewProgressResponse:
        run_path = self._validated_run_path()
        claims = self._load_claims(run_path / "claims.jsonl")
        original_submission = self._read_text(
            run_path / "intake.md", "original submission"
        )
        output = self._current_output(run_path / "output")
        evidence_by_claim = self._load_evidence(output, claims)
        validation_frames = self._load_validation_frames(
            run_path / "claim-mathematics.json",
            evidence_by_claim,
        )
        assessments = self._load_assessments(output, claims)
        manifest = self._load_manifest(output)

        items = []
        counts = {status.value: 0 for status in LiteratureClaimStatus}
        for claim in claims:
            evidence = evidence_by_claim.get(claim.claim_id, {})
            assessment = assessments.get(claim.claim_id)
            status = None
            summary = None
            corrected_claim = None
            assumptions: list[str] = []
            source_requests: list[str] = []
            cited: list[LiteratureEvidenceReferenceResponse] = []
            if assessment is not None:
                status = LiteratureClaimStatus(
                    self._string(assessment, "status")
                )
                counts[status.value] += 1
                summary = self._string(assessment, "summary")
                corrected_claim = self._optional_string(
                    assessment, "corrected_claim"
                )
                assumptions = self._string_list(assessment, "assumptions")
                source_requests = self._string_list(
                    assessment, "source_requests"
                )
                for label in self._string_list(assessment, "citations"):
                    source = evidence.get(label)
                    if source is None:
                        raise LiteratureReviewUnavailable(
                            "an assessment cites unavailable evidence"
                        )
                    cited.append(
                        LiteratureEvidenceReferenceResponse(
                            label=label,
                            citation_key=self._optional_string(
                                source, "citation_key"
                            ),
                            physical_page=self._positive_int(
                                source, "physical_page"
                            ),
                            quote=self._string(source, "text"),
                        )
                    )
            items.append(
                LiteratureClaimProgressResponse(
                    claim_id=claim.claim_id,
                    section=claim.section,
                    claim=claim.claim,
                    evidence_count=len(evidence),
                    status=status,
                    summary=summary,
                    corrected_claim=corrected_claim,
                    assumptions=assumptions,
                    evidence=cited,
                    source_requests=source_requests,
                    validation_frame=validation_frames.get(claim.claim_id),
                )
            )

        evidence_ready = sum(bool(item) for item in evidence_by_claim.values())
        assessment_count = len(assessments)
        phase = self._phase(
            len(claims), evidence_ready, assessment_count, output
        )
        completion = 100.0 * assessment_count / len(claims) if claims else 0.0
        return LiteratureReviewProgressResponse(
            run_id=run_path.name,
            phase=phase,
            assessment_status=(
                self._manifest_string(manifest, "assessment_status")
                or ("AUTOMATED_UNREVIEWED" if assessments else "NOT_RUN")
            ),
            claim_count=len(claims),
            evidence_ready_count=evidence_ready,
            assessment_count=assessment_count,
            completion_percent=round(completion, 1),
            status_counts=LiteratureStatusCountResponse(
                supported=counts["SUPPORTED"],
                qualified=counts["QUALIFIED"],
                contradicted=counts["CONTRADICTED"],
                unresolved=counts["UNRESOLVED"],
            ),
            human_disposition=self._manifest_string(
                manifest, "human_disposition"
            ),
            classifier_implementation_authorized=self._manifest_bool(
                manifest, "classifier_implementation_authorized"
            ),
            scientific_calculation_authorized=self._manifest_bool(
                manifest, "scientific_calculation_authorized"
            ),
            original_submission_markdown=original_submission,
            claims=items,
        )

    def provided_references(self) -> ProvidedReferenceListResponse:
        run_path = self._validated_run_path()
        store = ProvidedReferenceIntakeStore(run_path / "provided-references")
        try:
            items = [
                self._provided_reference_response(item) for item in store.list()
            ]
        except ProvidedReferenceIntakeError as error:
            raise LiteratureReviewUnavailable(str(error)) from error
        return ProvidedReferenceListResponse(items=items)

    def provide_reference(
        self,
        *,
        claim_id: str,
        citation_label: str,
        doi_or_url: str | None,
        note: str,
        pdf_bytes: bytes,
    ) -> ProvidedReferenceResponse:
        run_path = self._validated_run_path()
        claims = self._load_claims(run_path / "claims.jsonl")
        if claim_id not in {claim.claim_id for claim in claims}:
            raise InvalidProvidedReference("claim identity is not in this run")
        store = ProvidedReferenceIntakeStore(run_path / "provided-references")
        try:
            record = store.receive(
                claim_id=claim_id,
                citation_label=citation_label,
                doi_or_url=doi_or_url,
                note=note,
                pdf_bytes=pdf_bytes,
            )
        except ReferenceIntakeInvalid as error:
            raise InvalidProvidedReference(str(error)) from error
        except ProvidedReferenceIntakeError as error:
            raise LiteratureReviewUnavailable(str(error)) from error
        return self._provided_reference_response(record)

    def _provided_reference_response(
        self, record: IntakeProvidedReference
    ) -> ProvidedReferenceResponse:
        return ProvidedReferenceResponse(
            receipt_id=record.receipt_id,
            claim_id=record.claim_id,
            citation_label=record.citation_label,
            doi_or_url=record.doi_or_url,
            note=record.note,
            source_sha256=record.source_sha256,
            byte_length=record.byte_length,
            status=ProvidedReferenceStatus(record.status.value),
            received_at_utc=record.received_at_utc,
            latest_generation=record.latest_generation,
            duplicate=record.duplicate,
        )

    def _validated_run_path(self) -> Path:
        if self.run_path is None:
            raise LiteratureReviewUnavailable(
                "literature-review monitoring is not configured"
            )
        candidate = self.run_path.expanduser()
        if candidate.is_symlink():
            raise LiteratureReviewUnavailable(
                "symlinked literature-review runs are not accepted"
            )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise LiteratureReviewUnavailable(
                "the configured literature-review run is unavailable"
            ) from error
        if not resolved.is_dir() or _RUN_ID.fullmatch(resolved.name) is None:
            raise LiteratureReviewUnavailable(
                "the configured literature-review run is invalid"
            )
        return resolved

    def _current_output(self, output_root: Path) -> Path | None:
        if not output_root.is_dir() or output_root.is_symlink():
            return None
        candidates = [
            item
            for item in output_root.iterdir()
            if item.is_dir() and not item.is_symlink()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.stat().st_mtime_ns)

    def _load_claims(self, path: Path) -> tuple[_Claim, ...]:
        text = self._read_text(path, "claim inventory")
        claims = []
        seen = set()
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            value = self._json_object(line, f"claim line {line_number}")
            claim_id = self._string(value, "claim_id")
            if claim_id in seen or _RUN_ID.fullmatch(claim_id) is None:
                raise LiteratureReviewUnavailable(
                    "the claim inventory contains an invalid identity"
                )
            seen.add(claim_id)
            claims.append(
                _Claim(
                    claim_id=claim_id,
                    section=self._string(value, "section"),
                    claim=self._string(value, "claim"),
                )
            )
        if not claims or len(claims) > 100:
            raise LiteratureReviewUnavailable(
                "the claim inventory has an invalid size"
            )
        return tuple(claims)

    def _load_evidence(
        self,
        output: Path | None,
        claims: tuple[_Claim, ...],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        result: dict[str, dict[str, dict[str, Any]]] = {
            claim.claim_id: {} for claim in claims
        }
        if output is None:
            return result
        directory = output / "evidence"
        if not directory.is_dir() or directory.is_symlink():
            return result
        for claim in claims:
            path = directory / f"{claim.claim_id}.json"
            if not path.is_file() or path.is_symlink():
                continue
            payload = self._json_file(path, "evidence bundle")
            raw_items = payload.get("evidence")
            if not isinstance(raw_items, list) or len(raw_items) > 12:
                raise LiteratureReviewUnavailable(
                    "an evidence bundle has invalid contents"
                )
            by_label: dict[str, dict[str, Any]] = {}
            for item in raw_items:
                if not isinstance(item, dict):
                    raise LiteratureReviewUnavailable(
                        "an evidence reference is invalid"
                    )
                label = self._string(item, "label")
                if label in by_label:
                    raise LiteratureReviewUnavailable(
                        "an evidence bundle contains duplicate labels"
                    )
                by_label[label] = item
            result[claim.claim_id] = by_label
        return result

    def _load_validation_frames(
        self,
        path: Path,
        evidence_by_claim: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, LiteratureValidationFrameResponse]:
        if not path.exists():
            return {}
        if path.is_symlink() or not path.is_file():
            raise LiteratureReviewUnavailable(
                "claim-mathematics record is unavailable"
            )
        payload = self._json_file(path, "claim-mathematics record")
        assessment_status = self._string(payload, "assessment_status")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or len(raw_items) > 100:
            raise LiteratureReviewUnavailable(
                "claim-mathematics items are invalid"
            )
        result: dict[str, LiteratureValidationFrameResponse] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise LiteratureReviewUnavailable(
                    "claim-mathematics item is invalid"
                )
            claim_id = self._string(raw, "claim_id")
            if claim_id in result or claim_id not in evidence_by_claim:
                raise LiteratureReviewUnavailable(
                    "claim-mathematics identity is invalid"
                )
            evidence_labels = self._string_list(raw, "evidence_labels")
            available_labels = set(evidence_by_claim[claim_id])
            if any(label not in available_labels for label in evidence_labels):
                raise LiteratureReviewUnavailable(
                    "claim-mathematics evidence label is unavailable"
                )
            raw_equations = raw.get("equations")
            if (
                not isinstance(raw_equations, list)
                or not raw_equations
                or len(raw_equations) > 12
            ):
                raise LiteratureReviewUnavailable(
                    "claim-mathematics equations are invalid"
                )
            equations = []
            for equation in raw_equations:
                if not isinstance(equation, dict):
                    raise LiteratureReviewUnavailable(
                        "claim-mathematics equation is invalid"
                    )
                equations.append(
                    LiteratureEquationResponse(
                        label=self._string(equation, "label"),
                        latex=self._string(equation, "latex"),
                        interpretation=self._string(equation, "interpretation"),
                    )
                )
            result[claim_id] = LiteratureValidationFrameResponse(
                assessment_status=assessment_status,
                finding=self._string(raw, "finding"),
                conclusion=self._string(raw, "conclusion"),
                evidence_labels=evidence_labels,
                equations=equations,
            )
        return result

    def _load_assessments(
        self,
        output: Path | None,
        claims: tuple[_Claim, ...],
    ) -> dict[str, dict[str, Any]]:
        if output is None:
            return {}
        directory = output / "assessments"
        if not directory.is_dir() or directory.is_symlink():
            return {}
        result = {}
        for claim in claims:
            path = directory / f"{claim.claim_id}.json"
            if path.is_file() and not path.is_symlink():
                payload = self._json_file(path, "claim assessment")
                if self._string(payload, "claim_id") != claim.claim_id:
                    raise LiteratureReviewUnavailable(
                        "an assessment identity does not match its claim"
                    )
                result[claim.claim_id] = payload
        return result

    def _load_manifest(self, output: Path | None) -> dict[str, Any]:
        if output is None:
            return {}
        path = output / "manifest.json"
        if not path.is_file() or path.is_symlink():
            return {}
        return self._json_file(path, "literature-review manifest")

    def _phase(
        self,
        claim_count: int,
        evidence_ready: int,
        assessment_count: int,
        output: Path | None,
    ) -> LiteratureReviewPhase:
        if assessment_count == claim_count and claim_count > 0:
            return LiteratureReviewPhase.COMPLETE
        if assessment_count > 0:
            return LiteratureReviewPhase.ASSESSING
        if output is not None or evidence_ready > 0:
            return LiteratureReviewPhase.RETRIEVING
        return LiteratureReviewPhase.PENDING

    def _read_text(self, path: Path, label: str) -> str:
        if path.is_symlink() or not path.is_file():
            raise LiteratureReviewUnavailable(f"{label} is unavailable")
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise LiteratureReviewUnavailable(f"{label} exceeds its size limit")
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            message = f"{label} is unreadable"
            raise LiteratureReviewUnavailable(message) from error

    def _json_file(self, path: Path, label: str) -> dict[str, Any]:
        return self._json_object(self._read_text(path, label), label)

    def _json_object(self, text: str, label: str) -> dict[str, Any]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            message = f"{label} is invalid JSON"
            raise LiteratureReviewUnavailable(message) from error
        if not isinstance(value, dict):
            raise LiteratureReviewUnavailable(f"{label} must be an object")
        return value

    def _string(self, value: dict[str, Any], key: str) -> str:
        item = value.get(key)
        if not isinstance(item, str) or not item or len(item) > 10_000:
            raise LiteratureReviewUnavailable(f"{key} is invalid")
        return item

    def _optional_string(self, value: dict[str, Any], key: str) -> str | None:
        item = value.get(key)
        if item is None:
            return None
        if not isinstance(item, str) or not item or len(item) > 10_000:
            raise LiteratureReviewUnavailable(f"{key} is invalid")
        return item

    def _string_list(self, value: dict[str, Any], key: str) -> list[str]:
        items = value.get(key)
        if not isinstance(items, list) or len(items) > 32:
            raise LiteratureReviewUnavailable(f"{key} is invalid")
        if any(
            not isinstance(item, str) or not item or len(item) > 10_000
            for item in items
        ):
            raise LiteratureReviewUnavailable(f"{key} is invalid")
        return items

    def _positive_int(self, value: dict[str, Any], key: str) -> int:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise LiteratureReviewUnavailable(f"{key} is invalid")
        return item

    def _manifest_string(
        self, manifest: dict[str, Any], key: str
    ) -> str | None:
        item = manifest.get(key)
        return item if isinstance(item, str) and item else None

    def _manifest_bool(self, manifest: dict[str, Any], key: str) -> bool:
        item = manifest.get(key)
        return item if isinstance(item, bool) else False
