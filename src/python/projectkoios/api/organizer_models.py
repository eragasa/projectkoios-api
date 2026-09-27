from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from projectkoios.api.course_models import CourseCode
from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256 = r"^[0-9a-f]{64}$"


class OrganizerControlMode(StrEnum):
    ON = "on"
    PAUSE = "pause"
    OFF = "off"


class OrganizerActivity(StrEnum):
    OFF = "off"
    PAUSED = "paused"
    IDLE = "idle"
    DISCOVERING = "discovering"
    SCANNING = "scanning"
    CLASSIFYING = "classifying"
    FAILED = "failed"


class OrganizerFileAvailability(StrEnum):
    LOCAL = "local"
    CLOUD_PLACEHOLDER = "cloud_placeholder"
    INACCESSIBLE = "inaccessible"


class OrganizerParaCategory(StrEnum):
    PROJECT = "project"
    AREA = "area"
    RESOURCE = "resource"
    ARCHIVE = "archive"
    INBOX = "inbox"


class LifeDomain(StrEnum):
    RESEARCH = "research"
    TEACHING = "teaching"
    SOFTWARE = "software"
    BUSINESS = "business"
    PERSONAL = "personal"
    ADMINISTRATION = "administration"
    FINANCE = "finance"
    HEALTH = "health"
    MEDIA = "media"
    OTHER = "other"


class OrganizerControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: OrganizerControlMode


class OrganizerStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desired_mode: OrganizerControlMode
    activity: OrganizerActivity
    discovered_roots: int = Field(ge=0)
    observed_files: int = Field(ge=0)
    local_files: int = Field(ge=0)
    placeholder_files: int = Field(ge=0)
    proposed_files: int = Field(ge=0)
    last_event_sequence: int = Field(ge=0)
    current_root_id: str | None = Field(default=None, pattern=_SHA256)
    current_relative_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
    )
    last_error: str | None = Field(default=None, max_length=2000)


class OrganizerProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(pattern=_SHA256)
    root_id: str = Field(pattern=_SHA256)
    relative_path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=1024)
    extension: str = Field(max_length=128)
    byte_size: int = Field(ge=0)
    availability: OrganizerFileAvailability
    para_category: OrganizerParaCategory
    life_domain: LifeDomain
    course_code: CourseCode | None
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_group: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)
    model_digest: str = Field(pattern=_SHA256)
    proposed_at: datetime


class OrganizerProposalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: tuple[OrganizerProposalResponse, ...] = Field(max_length=500)
    total: int = Field(ge=0)
    complete: bool

    @model_validator(mode="after")
    def has_consistent_completion(self) -> OrganizerProposalListResponse:
        if self.total < len(self.proposals):
            raise ValueError("proposal total cannot be smaller than the page")
        if self.complete is not (len(self.proposals) == self.total):
            raise ValueError("proposal completion must match the bounded page")
        return self
