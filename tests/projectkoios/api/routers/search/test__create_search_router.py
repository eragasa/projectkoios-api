# tests/projectkoios/api/routers/search/test__create_search_router.py

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
                    source_path=Path(
                        "knowledge/quantum/particle_in_a_box.md"
                    ),
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
def client() -> TestClient:
    """
    Create a TestClient containing only the search router.

    This isolates search router behavior from full ProjectKoiosApp
    composition.
    """

    app = FastAPI()
    app.include_router(create_search_router(FakeSearchService()))

    return TestClient(app)


def test__search_endpoint__returns_results(client: TestClient) -> None:
    response = client.post(
        "/search",
        json={
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


def test__search_endpoint__rejects_empty_query(client: TestClient) -> None:
    response = client.post(
        "/search",
        json={
            "query": "",
            "limit": 10,
        },
    )

    assert response.status_code == 422


def test__search_endpoint__rejects_limit_above_maximum(
    client: TestClient,
) -> None:
    response = client.post(
        "/search",
        json={
            "query": "particle",
            "limit": 100,
        },
    )

    assert response.status_code == 422