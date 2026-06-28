# tests/projectkoios/api/routers/core/test__create_core_router.py

"""
Tests for the core router factory.

These tests verify that create_core_router() produces a router with the
expected root and health-check endpoints.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.routers.core import create_core_router


@pytest.fixture
def client() -> TestClient:
    """
    Create a TestClient containing only the core router.

    This isolates CoreRouter behavior from ProjectKoiosApp composition.
    """

    app = FastAPI()
    app.include_router(create_core_router())

    return TestClient(app)


def test__root_endpoint__returns_project_message(client: TestClient) -> None:
    """
    GET / should return the root Project Koios message.
    """

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Hello, Project Koios",
    }


def test__health_endpoint__returns_ok(client: TestClient) -> None:
    """
    GET /health should return a simple health-check response.
    """

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }