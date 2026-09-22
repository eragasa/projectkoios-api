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


class OrganizerProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    root_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=1024)
    extension: str = Field(max_length=128)
    byte_size: int = Field(ge=0)
    availability: Literal["local", "cloud_placeholder", "inaccessible"]
    para_category: Literal["project", "area", "resource", "archive", "inbox"]
    life_domain: Literal[
        "research",
        "teaching",
        "software",
        "business",
        "personal",
        "administration",
        "finance",
        "health",
        "media",
        "other",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_group: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)
    model_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_at: str


class OrganizerProposalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[OrganizerProposalResponse]
    total: int = Field(ge=0)
    complete: bool


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
