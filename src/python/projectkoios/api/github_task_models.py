from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

_REPOSITORY_IDENTITY = (
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
)
_GIT_SHA = r"^[0-9a-f]{40}$"


class GitHubTask(BaseModel):
    sequence_index: int = Field(ge=1)
    job_name: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=40)
    conclusion: str | None = Field(default=None, max_length=40)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GitHubTaskSequence(BaseModel):
    run_id: int = Field(ge=1)
    workflow_name: str = Field(min_length=1, max_length=200)
    event: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=40)
    conclusion: str | None = Field(default=None, max_length=40)
    branch: str = Field(min_length=1, max_length=255)
    commit_sha: str = Field(pattern=_GIT_SHA)
    url: HttpUrl
    created_at: datetime
    tasks: tuple[GitHubTask, ...] = ()
    tasks_complete: bool = True


class GitHubPullRequestSummary(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    is_draft: bool
    head_branch: str = Field(min_length=1, max_length=255)
    head_sha: str = Field(pattern=_GIT_SHA)
    base_branch: str = Field(min_length=1, max_length=255)


class GitHubRepositoryTaskProjection(BaseModel):
    repository: str = Field(pattern=_REPOSITORY_IDENTITY)
    state: Literal["ok", "error"]
    error_kind: str | None = Field(default=None, max_length=80)
    default_branch: str | None = Field(default=None, max_length=255)
    open_pull_requests: tuple[GitHubPullRequestSummary, ...] = ()
    open_pull_requests_complete: bool = True
    latest_sequence: GitHubTaskSequence | None = None


class GitHubTaskDashboard(BaseModel):
    source: Literal["github-live"] = "github-live"
    repositories: tuple[GitHubRepositoryTaskProjection, ...] = ()
