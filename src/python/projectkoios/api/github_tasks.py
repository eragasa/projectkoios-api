from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from projectkoios.api.github_task_models import (
    GitHubPullRequestSummary,
    GitHubRepositoryTaskProjection,
    GitHubTask,
    GitHubTaskDashboard,
    GitHubTaskSequence,
)
from pydantic import HttpUrl, ValidationError

_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
)
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class GitHubTaskReadError(RuntimeError):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class GitHubTaskReader:
    """Read bounded GitHub task projections through the authenticated CLI."""

    def __init__(
        self,
        repositories: tuple[str, ...],
        *,
        executable: str | Path = "gh",
        timeout_seconds: float = 15.0,
    ) -> None:
        for repository in repositories:
            if _REPOSITORY.fullmatch(repository) is None:
                raise ValueError(
                    f"invalid GitHub repository identity: {repository}"
                )
        self.repositories = repositories
        self.executable = str(executable)
        self.timeout_seconds = timeout_seconds

    def read_dashboard(self) -> GitHubTaskDashboard:
        projections = tuple(
            self._read_repository_or_error(repository)
            for repository in self.repositories
        )
        return GitHubTaskDashboard(repositories=projections)

    def _read_repository_or_error(
        self,
        repository: str,
    ) -> GitHubRepositoryTaskProjection:
        try:
            return self._read_repository(repository)
        except GitHubTaskReadError as error:
            return GitHubRepositoryTaskProjection(
                repository=repository,
                state="error",
                error_kind=error.kind,
            )

    def _read_repository(
        self,
        repository: str,
    ) -> GitHubRepositoryTaskProjection:
        try:
            metadata = self._mapping(self._api(f"repos/{repository}"))
            default_branch = self._text(metadata, "default_branch", 255)
            pull_requests, pull_requests_complete = self._pull_requests(
                repository
            )
            latest_sequence = self._latest_sequence(repository)
            return GitHubRepositoryTaskProjection(
                repository=repository,
                state="ok",
                default_branch=default_branch,
                open_pull_requests=pull_requests,
                open_pull_requests_complete=pull_requests_complete,
                latest_sequence=latest_sequence,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise GitHubTaskReadError("invalid_response") from error

    def _pull_requests(
        self,
        repository: str,
    ) -> tuple[tuple[GitHubPullRequestSummary, ...], bool]:
        payload = self._sequence(
            self._api(f"repos/{repository}/pulls?state=open&per_page=20")
        )
        pull_requests = []
        for item in payload:
            pull_request = self._mapping(item)
            number = self._integer(pull_request, "number")
            head = self._mapping(pull_request["head"])
            base = self._mapping(pull_request["base"])
            pull_requests.append(
                GitHubPullRequestSummary(
                    number=number,
                    title=self._text(pull_request, "title", 500),
                    url=HttpUrl(
                        f"https://github.com/{repository}/pull/{number}"
                    ),
                    is_draft=self._boolean(pull_request, "draft"),
                    head_branch=self._text(head, "ref", 255),
                    head_sha=self._text(head, "sha", 40),
                    base_branch=self._text(base, "ref", 255),
                )
            )
        return (
            tuple(sorted(pull_requests, key=lambda item: item.number)),
            len(payload) < 20,
        )

    def _latest_sequence(
        self,
        repository: str,
    ) -> GitHubTaskSequence | None:
        payload = self._mapping(
            self._api(f"repos/{repository}/actions/runs?per_page=1")
        )
        runs = self._sequence(payload["workflow_runs"])
        if not runs:
            return None
        run = self._mapping(runs[0])
        run_id = self._integer(run, "id")
        tasks, tasks_complete = self._tasks(repository, run_id)
        return GitHubTaskSequence(
            run_id=run_id,
            workflow_name=self._text(run, "name", 200),
            event=self._text(run, "event", 80),
            status=self._text(run, "status", 40),
            conclusion=self._optional_text(run, "conclusion", 40),
            branch=self._text(run, "head_branch", 255),
            commit_sha=self._text(run, "head_sha", 40),
            url=HttpUrl(
                f"https://github.com/{repository}/actions/runs/{run_id}"
            ),
            created_at=self._datetime(run, "created_at"),
            tasks=tasks,
            tasks_complete=tasks_complete,
        )

    def _tasks(
        self,
        repository: str,
        run_id: int,
    ) -> tuple[tuple[GitHubTask, ...], bool]:
        payload = self._mapping(
            self._api(
                f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=20"
            )
        )
        jobs = sorted(
            (self._mapping(job) for job in self._sequence(payload["jobs"])),
            key=lambda job: self._integer(job, "id"),
        )
        tasks = []
        sequence_index = 1
        for job in jobs:
            job_name = self._text(job, "name", 200)
            steps = sorted(
                (
                    self._mapping(step)
                    for step in self._sequence(job.get("steps", []))
                ),
                key=lambda step: self._integer(step, "number"),
            )
            for step in steps:
                task_name = self._text(step, "name", 200)
                if not task_name.startswith("GitHubTask "):
                    continue
                tasks.append(
                    GitHubTask(
                        sequence_index=sequence_index,
                        job_name=job_name,
                        name=task_name,
                        status=self._text(step, "status", 40),
                        conclusion=self._optional_text(step, "conclusion", 40),
                        started_at=self._optional_datetime(step, "started_at"),
                        completed_at=self._optional_datetime(
                            step, "completed_at"
                        ),
                    )
                )
                sequence_index += 1
        return (
            tuple(tasks),
            self._nonnegative_integer(payload, "total_count") <= len(jobs),
        )

    def _api(self, endpoint: str) -> Any:
        try:
            result = subprocess.run(
                [
                    self.executable,
                    "api",
                    "--method",
                    "GET",
                    "-H",
                    "Accept: application/vnd.github+json",
                    endpoint,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise GitHubTaskReadError("cli_unavailable") from error
        except subprocess.TimeoutExpired as error:
            raise GitHubTaskReadError("timeout") from error

        if result.returncode != 0:
            error_text = result.stderr.lower()
            if "authentication" in error_text or "401" in error_text:
                kind = "authentication"
            elif "rate limit" in error_text or "403" in error_text:
                kind = "rate_limited"
            elif "not found" in error_text or "404" in error_text:
                kind = "not_found"
            else:
                kind = "github_error"
            raise GitHubTaskReadError(kind)
        if len(result.stdout.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise GitHubTaskReadError("response_too_large")
        try:
            return json.loads(
                result.stdout,
                object_pairs_hook=self._reject_duplicate_fields,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise GitHubTaskReadError("invalid_response") from error

    @staticmethod
    def _reject_duplicate_fields(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("expected object")
        return value

    @staticmethod
    def _sequence(value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise TypeError("expected array")
        return value

    @classmethod
    def _text(
        cls,
        value: Mapping[str, Any],
        key: str,
        maximum: int,
    ) -> str:
        raw = value[key]
        if not isinstance(raw, str):
            raise TypeError(f"{key} must be a string")
        cleaned = "".join(
            character
            for character in raw
            if character >= " " and character != "\x7f"
        ).strip()
        if not cleaned or len(cleaned) > maximum:
            raise ValueError(f"{key} is outside its display bound")
        return cleaned

    @classmethod
    def _optional_text(
        cls,
        value: Mapping[str, Any],
        key: str,
        maximum: int,
    ) -> str | None:
        if value.get(key) is None:
            return None
        return cls._text(value, key, maximum)

    @classmethod
    def _datetime(
        cls,
        value: Mapping[str, Any],
        key: str,
    ) -> datetime:
        result = datetime.fromisoformat(
            cls._text(value, key, 80).replace("Z", "+00:00")
        )
        if result.tzinfo is None:
            raise ValueError(f"{key} must include a timezone")
        return result

    @classmethod
    def _optional_datetime(
        cls,
        value: Mapping[str, Any],
        key: str,
    ) -> datetime | None:
        if value.get(key) is None:
            return None
        return cls._datetime(value, key)

    @staticmethod
    def _integer(value: Mapping[str, Any], key: str) -> int:
        result = value[key]
        if (
            isinstance(result, bool)
            or not isinstance(result, int)
            or result < 1
        ):
            raise TypeError(f"{key} must be a positive integer")
        return result

    @staticmethod
    def _nonnegative_integer(value: Mapping[str, Any], key: str) -> int:
        result = value[key]
        if (
            isinstance(result, bool)
            or not isinstance(result, int)
            or result < 0
        ):
            raise TypeError(f"{key} must be a nonnegative integer")
        return result

    @staticmethod
    def _boolean(value: Mapping[str, Any], key: str) -> bool:
        result = value[key]
        if not isinstance(result, bool):
            raise TypeError(f"{key} must be a boolean")
        return result
