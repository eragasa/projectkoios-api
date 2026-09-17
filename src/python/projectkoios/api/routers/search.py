from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from projectkoios.api.models import SearchRequest, SearchResult
from projectkoios.search.models import ChunkSearchResult


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[ChunkSearchResult]: ...


def create_search_router(
    search_service: SearchProvider,
) -> APIRouter:
    router = APIRouter(prefix="/search", tags=["search"])

    @router.post("", response_model=list[SearchResult])
    def search(request: SearchRequest) -> list[SearchResult]:
        results = search_service.search(
            query=request.query,
            limit=request.limit,
        )

        return [
            SearchResult(
                title=result.chunk.source_path.name,
                path=str(result.chunk.source_path),
                snippet=result.chunk.text,
                score=result.score,
                object_type=result.chunk.source_kind,
            )
            for result in results
        ]

    return router
