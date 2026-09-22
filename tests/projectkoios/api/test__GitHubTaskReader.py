import json
import subprocess
from collections.abc import Callable
from typing import Any

from projectkoios.api.github_tasks import GitHubTaskReader

_REPOSITORY = "eragasa/projectkoios-api"
_RUN_ID = 35712169373
_SHA = "e" * 40


def _completed(payload: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def _github_response(endpoint: str) -> subprocess.CompletedProcess[str]:
    responses = {
        f"repos/{_REPOSITORY}": {"default_branch": "master"},
        f"repos/{_REPOSITORY}/pulls?state=open&per_page=20": [
            {
                "number": 4,
                "title": "Add a read-only task dashboard",
                "draft": False,
                "head": {"ref": "work/dashboard", "sha": _SHA},
                "base": {"ref": "master"},
            }
        ],
        f"repos/{_REPOSITORY}/actions/runs?per_page=1": {
            "workflow_runs": [
                {
                    "id": _RUN_ID,
                    "name": "CI",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "master",
                    "head_sha": _SHA,
                    "created_at": "2026-09-22T09:45:19Z",
                }
            ]
        },
        f"repos/{_REPOSITORY}/actions/runs/{_RUN_ID}/jobs?per_page=20": {
            "total_count": 1,
            "jobs": [
                {
                    "id": 2,
                    "name": "Python 3.14 task sequence",
                    "steps": [
                        {
                            "number": 2,
                            "name": "GitHubTask 02 · Test",
                            "status": "completed",
                            "conclusion": "success",
                            "started_at": "2026-09-22T09:45:20Z",
                            "completed_at": "2026-09-22T09:45:22Z",
                        },
                        {
                            "number": 1,
                            "name": "GitHubTask 01 · Checkout",
                            "status": "completed",
                            "conclusion": "success",
                            "started_at": "2026-09-22T09:45:19Z",
                            "completed_at": "2026-09-22T09:45:20Z",
                        },
                        {
                            "number": 3,
                            "name": "Complete job",
                            "status": "completed",
                            "conclusion": "success",
                            "started_at": "2026-09-22T09:45:22Z",
                            "completed_at": "2026-09-22T09:45:23Z",
                        },
                    ],
                }
            ],
        },
    }
    return _completed(responses[endpoint])


def _fake_run(
    response: Callable[[str], subprocess.CompletedProcess[str]],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert command[:6] == [
            "gh",
            "api",
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
        ]
        return response(command[-1])

    return run


def test__read_dashboard__returns_empty_projection_without_repositories() -> (
    None
):
    dashboard = GitHubTaskReader(()).read_dashboard()

    assert dashboard.source == "github-live"
    assert dashboard.repositories == ()


def test__read_dashboard__projects_pull_requests_and_ordered_tasks(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(_github_response))

    dashboard = GitHubTaskReader((_REPOSITORY,)).read_dashboard()

    repository = dashboard.repositories[0]
    assert repository.state == "ok"
    assert repository.default_branch == "master"
    assert repository.open_pull_requests[0].number == 4
    assert repository.open_pull_requests_complete is True
    assert str(repository.open_pull_requests[0].url) == (
        "https://github.com/eragasa/projectkoios-api/pull/4"
    )
    assert repository.latest_sequence is not None
    assert repository.latest_sequence.run_id == _RUN_ID
    assert repository.latest_sequence.tasks_complete is True
    assert [task.name for task in repository.latest_sequence.tasks] == [
        "GitHubTask 01 · Checkout",
        "GitHubTask 02 · Test",
    ]
    assert [
        task.sequence_index for task in repository.latest_sequence.tasks
    ] == [1, 2]


def test__read_dashboard__marks_bounded_collections_incomplete(
    monkeypatch: Any,
) -> None:
    def truncated(endpoint: str) -> subprocess.CompletedProcess[str]:
        response = _github_response(endpoint)
        payload = json.loads(response.stdout)
        if endpoint.endswith("pulls?state=open&per_page=20"):
            template = payload[0]
            payload = [
                {**template, "number": number} for number in range(1, 21)
            ]
        elif endpoint.endswith("jobs?per_page=20"):
            payload["total_count"] = 2
        return _completed(payload)

    monkeypatch.setattr(subprocess, "run", _fake_run(truncated))

    repository = (
        GitHubTaskReader((_REPOSITORY,)).read_dashboard().repositories[0]
    )

    assert repository.open_pull_requests_complete is False
    assert repository.latest_sequence is not None
    assert repository.latest_sequence.tasks_complete is False


def test__read_dashboard__reports_bounded_error_without_raw_cli_output(
    monkeypatch: Any,
) -> None:
    def unauthorized(_: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gh"],
            returncode=1,
            stdout="",
            stderr="HTTP 401 authentication token secret-value",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run(unauthorized))

    repository = (
        GitHubTaskReader((_REPOSITORY,)).read_dashboard().repositories[0]
    )

    assert repository.state == "error"
    assert repository.error_kind == "authentication"
    assert "secret-value" not in repository.model_dump_json()


def test__read_dashboard__rejects_duplicate_json_fields(
    monkeypatch: Any,
) -> None:
    def duplicate(_: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout='{"default_branch":"master","default_branch":"main"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run(duplicate))

    repository = (
        GitHubTaskReader((_REPOSITORY,)).read_dashboard().repositories[0]
    )

    assert repository.state == "error"
    assert repository.error_kind == "invalid_response"
