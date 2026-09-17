# tests/projectkoios/api/routers/core/test__create_core_router.py

"""
Tests for the core router factory.

These tests verify that create_core_router() produces a router with the
expected root and health-check endpoints.
"""

import asyncio

import httpx2
import pytest
from fastapi import FastAPI
from projectkoios.api.routers.core import create_core_router


@pytest.fixture
def app() -> FastAPI:
    """Create an application containing only the core router."""
    application = FastAPI()
    application.include_router(create_core_router())
    return application


def _get(app: FastAPI, path: str) -> httpx2.Response:
    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(send())


def test__root_endpoint__returns_project_message(app: FastAPI) -> None:
    """
    GET / should return the root Project Koios message.
    """

    response = _get(app, "/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Hello, Project Koios",
    }


def test__health_endpoint__returns_ok(app: FastAPI) -> None:
    """
    GET /health should return a simple health-check response.
    """

    response = _get(app, "/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }