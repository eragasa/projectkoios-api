from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from projectkoios.api.citation_review_models import (
    CitationCandidateResponse,
    CitationDecisionDisposition,
    CitationDecisionRequest,
    CitationDecisionResponse,
    CitationReviewDetailResponse,
    CitationReviewQueueResponse,
    CitationReviewSummaryResponse,
    ManuscriptEquationResponse,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CitationReviewUnavailable(RuntimeError):
    pass


class CitationReviewNotFound(LookupError):
    pass


class InvalidCitationDecision(ValueError):
    pass


class CitationReviewBundleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    lines: str
    claim: str
    query: str
    manuscript_excerpt_latex: str
    manuscript_equations: list[ManuscriptEquationResponse]
    expected_keys: list[str]
    expected_keys_available: list[str]
    expected_outcome: str
    evaluation_status: str
    recommendation_relationship: str
    recommended_keys: list[str]
    recommendation: str
    candidates: list[CitationCandidateResponse]


class CitationReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    assessment: str
    manuscript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: list[CitationReviewBundleItem]


class CitationReviewRepository:
    def __init__(
        self,
        bundle_path: Path,
        decisions_path: Path,
        sources_root: Path,
    ) -> None:
        self.bundle_path = bundle_path.expanduser()
        self.decisions_path = decisions_path.expanduser()
        self.sources_root = sources_root.expanduser()

    def queue(self) -> CitationReviewQueueResponse:
        bundle = self._bundle()
        decisions = self._decisions(bundle.manuscript_sha256)
        items = [
            self._summary(item, decisions.get(item.claim_id))
            for item in bundle.items
        ]
        return CitationReviewQueueResponse(
            assessment=bundle.assessment,
            manuscript_sha256=bundle.manuscript_sha256,
            total=len(items),
            decided=sum(item.decision is not None for item in items),
            items=items,
        )

    def detail(self, claim_id: str) -> CitationReviewDetailResponse:
        bundle = self._bundle()
        item = next(
            (
                candidate
                for candidate in bundle.items
                if candidate.claim_id == claim_id
            ),
            None,
        )
        if item is None:
            raise CitationReviewNotFound(claim_id)
        decision = self._decisions(bundle.manuscript_sha256).get(claim_id)
        return CitationReviewDetailResponse(
            **self._summary(item, decision).model_dump(),
            query=item.query,
            manuscript_excerpt_latex=item.manuscript_excerpt_latex,
            manuscript_equations=item.manuscript_equations,
            expected_keys=item.expected_keys,
            expected_keys_available=item.expected_keys_available,
            expected_outcome=item.expected_outcome,
            recommendation=item.recommendation,
            candidates=item.candidates,
        )

    def source_path(self, source_name: str) -> Path:
        if Path(source_name).name != source_name or not source_name.endswith(
            ".pdf"
        ):
            raise CitationReviewNotFound(source_name)
        bundle = self._bundle()
        allowed = {
            candidate.file
            for item in bundle.items
            for candidate in item.candidates
        }
        if source_name not in allowed:
            raise CitationReviewNotFound(source_name)
        root = self.sources_root.resolve()
        candidate = root / source_name
        if candidate.is_symlink():
            raise CitationReviewNotFound(source_name)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise CitationReviewNotFound(source_name) from error
        if resolved.parent != root or not resolved.is_file():
            raise CitationReviewNotFound(source_name)
        return resolved

    def decide(
        self, claim_id: str, request: CitationDecisionRequest
    ) -> CitationDecisionResponse:
        detail = self.detail(claim_id)
        manuscript_sha256 = self._bundle().manuscript_sha256
        selected = tuple(dict.fromkeys(request.selected_citation_keys))
        if len(selected) != len(request.selected_citation_keys):
            raise InvalidCitationDecision(
                "selected citation keys must be unique"
            )
        available = {
            candidate.citation_key
            for candidate in detail.candidates
            if candidate.citation_key is not None
        }
        if any(key not in available for key in selected):
            raise InvalidCitationDecision(
                "selected citation keys must come from the displayed candidates"
            )
        requires_selection = request.disposition in {
            CitationDecisionDisposition.ACCEPT_CITATION,
            CitationDecisionDisposition.PARTIAL_SUPPORT,
        }
        if requires_selection and not selected:
            raise InvalidCitationDecision(
                "this disposition requires at least one selected citation"
            )
        if not requires_selection and selected:
            raise InvalidCitationDecision(
                "this disposition does not accept selected citations"
            )
        note = request.note.strip()
        self._initialize_decisions()
        with self._decision_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT MAX(revision) FROM citation_decisions
                WHERE manuscript_sha256 = ? AND claim_id = ?
                """,
                (manuscript_sha256, claim_id),
            ).fetchone()
            previous_revision = existing[0] if existing is not None else None
            revision = (
                1 if previous_revision is None else int(previous_revision) + 1
            )
            updated_at_utc = datetime.now(UTC).isoformat()
            connection.execute(
                """
                INSERT INTO citation_decisions(
                    manuscript_sha256, claim_id, revision, disposition,
                    selected_citation_keys_json, note, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manuscript_sha256,
                    claim_id,
                    revision,
                    request.disposition.value,
                    json.dumps(selected, separators=(",", ":")),
                    note,
                    updated_at_utc,
                ),
            )
        return CitationDecisionResponse(
            claim_id=claim_id,
            disposition=request.disposition,
            selected_citation_keys=list(selected),
            note=note,
            revision=revision,
            updated_at_utc=updated_at_utc,
        )

    def _bundle(self) -> CitationReviewBundle:
        path = self.bundle_path
        if path.is_symlink():
            raise CitationReviewUnavailable(
                "citation review bundle is a symlink"
            )
        try:
            stat = path.stat()
        except FileNotFoundError as error:
            raise CitationReviewUnavailable(
                "citation review bundle is not configured"
            ) from error
        if not path.is_file() or stat.st_size > 20_000_000:
            raise CitationReviewUnavailable(
                "citation review bundle must be a regular file under 20 MB"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            bundle = CitationReviewBundle.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise CitationReviewUnavailable(
                "citation review bundle is invalid"
            ) from error
        identifiers = [item.claim_id for item in bundle.items]
        if len(identifiers) != len(set(identifiers)):
            raise CitationReviewUnavailable(
                "citation review bundle contains duplicate claim identifiers"
            )
        if bundle.schema_version != "1":
            raise CitationReviewUnavailable(
                "citation review bundle schema is unsupported"
            )
        return bundle

    def _summary(
        self,
        item: CitationReviewBundleItem,
        decision: CitationDecisionResponse | None,
    ) -> CitationReviewSummaryResponse:
        return CitationReviewSummaryResponse(
            claim_id=item.claim_id,
            lines=item.lines,
            claim=item.claim,
            recommendation_relationship=item.recommendation_relationship,
            recommended_keys=item.recommended_keys,
            evaluation_status=item.evaluation_status,
            decision=decision,
        )

    def _decisions(
        self, manuscript_sha256: str
    ) -> dict[str, CitationDecisionResponse]:
        if not self.decisions_path.exists():
            return {}
        self._initialize_decisions()
        with self._decision_connection() as connection:
            rows = connection.execute(
                """
                SELECT claim_id, disposition, selected_citation_keys_json,
                       note, revision, updated_at_utc
                FROM citation_decisions
                WHERE manuscript_sha256 = ?
                ORDER BY claim_id, revision
                """,
                (manuscript_sha256,),
            ).fetchall()
        result: dict[str, CitationDecisionResponse] = {}
        for row in rows:
            try:
                selected = json.loads(row[2])
                result[row[0]] = CitationDecisionResponse(
                    claim_id=row[0],
                    disposition=CitationDecisionDisposition(row[1]),
                    selected_citation_keys=selected,
                    note=row[3],
                    revision=int(row[4]),
                    updated_at_utc=row[5],
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as error:
                raise CitationReviewUnavailable(
                    "stored citation review decision is invalid"
                ) from error
        return result

    def _initialize_decisions(self) -> None:
        path = self.decisions_path
        if path.is_symlink():
            raise CitationReviewUnavailable(
                "citation decision store is a symlink"
            )
        parent = path.parent
        if parent.is_symlink():
            raise CitationReviewUnavailable(
                "citation decision directory is a symlink"
            )
        parent_existed = parent.exists()
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if not parent_existed:
                os.chmod(parent, 0o700)
        except OSError as error:
            raise CitationReviewUnavailable(
                "citation decision directory is unavailable"
            ) from error
        with self._decision_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS citation_decisions (
                    manuscript_sha256 TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    disposition TEXT NOT NULL,
                    selected_citation_keys_json TEXT NOT NULL,
                    note TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (manuscript_sha256, claim_id, revision)
                )
                """
            )

    @contextmanager
    def _decision_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect_decisions()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _connect_decisions(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.decisions_path)
        try:
            os.chmod(self.decisions_path, 0o600)
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
        except (OSError, sqlite3.Error) as error:
            connection.close()
            raise CitationReviewUnavailable(
                "citation decision store is unavailable"
            ) from error
        return connection
