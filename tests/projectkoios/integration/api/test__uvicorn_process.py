# tests/integration/api_server/test__uvicorn_process.py

"""
Integration test for serving Project Koios through Uvicorn.

This test starts a real Uvicorn process and checks that the promoted ASGI
entry point can serve the health endpoint over HTTP.
"""

import multiprocessing
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

HOST = "127.0.0.1"
PORT = 8010
BASE_URL = f"http://{HOST}:{PORT}"


def run_uvicorn_server() -> None:
    """
    Run the Project Koios API through Uvicorn.

    This function runs in a separate process because uvicorn.run() blocks
    until the server is stopped.
    """

    uvicorn.run(
        "projectkoios.api.main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
    )


@pytest.fixture
def uvicorn_process() -> Iterator[multiprocessing.Process]:
    """
    Start Uvicorn in a separate process and stop it after the test.

    The fixture owns process lifecycle:

    - start server process
    - yield process to the test
    - terminate process during cleanup
    """

    process = multiprocessing.Process(target=run_uvicorn_server)
    process.start()

    try:
        yield process

    finally:
        process.terminate()
        process.join(timeout=5.0)


def wait_for_health_endpoint() -> httpx.Response | None:
    """
    Poll the health endpoint until the server is ready or the deadline expires.
    """

    deadline = time.time() + 10.0

    while time.time() < deadline:
        try:
            response = httpx.get(
                f"{BASE_URL}/health",
                timeout=1.0,
            )

            if response.status_code == 200:
                return response

        except httpx.ConnectError:
            time.sleep(0.1)

    return None


@pytest.mark.integration
def test__uvicorn_process__serves_health_endpoint(
    uvicorn_process: multiprocessing.Process,
) -> None:
    """
    Uvicorn should serve the Project Koios /health endpoint.
    """

    # This is a server smoke test, not a full endpoint behavior test.
    #
    # The purpose is to verify the real process path:
    #
    #     uvicorn
    #         imports projectkoios.api.main:app
    #         starts an HTTP server
    #         serves at least one request
    #
    # It should stay small because process tests are slower and more fragile
    # than in-process FastAPI tests.
    assert uvicorn_process.is_alive()

    response = wait_for_health_endpoint()

    assert response is not None
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Do not test every API endpoint here.
    #
    # Endpoint behavior belongs in TestClient-based router/API tests, such as:
    #
    #     tests/api/routers/core/test__create_core_router.py
    #         GET /
    #         GET /health
    #
    #     tests/api/routers/search/test__create_search_router.py
    #         POST /search
    #         request validation
    #         response serialization
    #
    # Service behavior belongs in direct service tests, such as:
    #
    #     tests/search/service/test__SearchService.py
    #
    # The Uvicorn integration test answers only:
    #
    #     Can the promoted ASGI app be imported and served by a real server?