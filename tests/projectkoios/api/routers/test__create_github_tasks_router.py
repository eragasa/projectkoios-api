import asyncio

import httpx2
from fastapi import FastAPI
from projectkoios.api.github_task_models import GitHubTaskDashboard
from projectkoios.api.routers.github_tasks import create_github_tasks_router


class StubGitHubTaskProvider:
    def read_dashboard(self) -> GitHubTaskDashboard:
        return GitHubTaskDashboard()


def test__read_github_tasks__returns_live_projection() -> None:
    application = FastAPI()
    application.include_router(
        create_github_tasks_router(StubGitHubTaskProvider())
    )

    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=application)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/github/tasks")

    response = asyncio.run(send())

    assert response.status_code == 200
    assert response.json() == {
        "source": "github-live",
        "repositories": [],
    }
