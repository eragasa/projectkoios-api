from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from projectkoios.api.github_task_models import GitHubTaskDashboard


class GitHubTaskProvider(Protocol):
    def read_dashboard(self) -> GitHubTaskDashboard: ...


def create_github_tasks_router(provider: GitHubTaskProvider) -> APIRouter:
    router = APIRouter(prefix="/github/tasks", tags=["github-tasks"])

    @router.get("", response_model=GitHubTaskDashboard)
    def read_github_tasks() -> GitHubTaskDashboard:
        return provider.read_dashboard()

    return router
