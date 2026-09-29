from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorResponse(BaseModel):
    """Stable HTTP error envelope exposed by API-owned routes."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(min_length=1, max_length=500)
