from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    object_types: list[str] | None = None

class SearchResult(BaseModel):
    title: str
    path: str
    snippet: str
    score: float
    object_type: str
