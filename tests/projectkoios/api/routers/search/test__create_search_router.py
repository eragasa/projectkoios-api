# tests/projectkoios/api/routers/search/test__create_search_router.py

import asyncio
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from projectkoios.api.routers.search import create_search_router
from projectkoios.chunking import TextChunk
from projectkoios.search.models import ChunkSearchResult


class FakeSearchService:
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[ChunkSearchResult]:
        results = [
            ChunkSearchResult(
                chunk=TextChunk(
                    source_path=Path("knowledge/quantum/particle_in_a_box.md"),
                    source_kind="note",
                    language="markdown",
                    chunk_index=0,
                    start_line=1,
                    end_line=1,
                    text=(
                        "The particle in a box is the canonical Dirichlet "
                        "boundary condition problem."
                    ),
                ),
                score=1.0,
            )
        ]

        return results[:limit]


@pytest.fixture
def app() -> FastAPI:
    """Create an application containing only the search router."""
    application = FastAPI()
    application.include_router(create_search_router(FakeSearchService()))
    return application


def _post(
    app: FastAPI,
    path: str,
    payload: dict[str, object],
) -> httpx2.Response:
    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(path, json=payload)

    return asyncio.run(send())


def test__search_endpoint__returns_results(app: FastAPI) -> None:
    response = _post(
        app,
        "/search",
        {
            "query": "particle",
            "limit": 10,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 1

    result = data[0]

    assert result["title"] == "particle_in_a_box.md"
    assert result["path"] == "knowledge/quantum/particle_in_a_box.md"
    assert result["snippet"] == (
        "The particle in a box is the canonical Dirichlet "
        "boundary condition problem."
    )
    assert result["score"] == 1.0
    assert result["object_type"] == "note"


def test__search_endpoint__rejects_empty_query(app: FastAPI) -> None:
    response = _post(
        app,
        "/search",
        {
            "query": "",
            "limit": 10,
        },
    )

    assert response.status_code == 422


def test__search_endpoint__rejects_limit_above_maximum(
    app: FastAPI,
) -> None:
    response = _post(
        app,
        "/search",
        {
            "query": "particle",
            "limit": 100,
        },
    )

    assert response.status_code == 422


def test__search_endpoint__rejects_unsupported_filters(
    app: FastAPI,
) -> None:
    response = _post(
        app,
        "/search",
        {
            "query": "particle",
            "object_types": ["note"],
        },
    )

    assert response.status_code == 422
