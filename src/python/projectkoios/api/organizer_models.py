from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrganizerControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["on", "pause", "off"]


class OrganizerStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desired_mode: Literal["on", "pause", "off"]
    activity: Literal[
        "off",
        "paused",
        "idle",
        "discovering",
        "scanning",
        "classifying",
        "failed",
    ]
    discovered_roots: int = Field(ge=0)
    observed_files: int = Field(ge=0)
    local_files: int = Field(ge=0)
    placeholder_files: int = Field(ge=0)
    proposed_files: int = Field(ge=0)
    last_event_sequence: int = Field(ge=0)
    current_root_id: str | None
    current_relative_path: str | None
    last_error: str | None


class OrganizerEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    occurred_at: str
    kind: str
    message: str
    root_id: str | None
    file_id: str | None


class OrganizerEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[OrganizerEventResponse]
