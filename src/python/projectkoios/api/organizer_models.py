from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from projectkoios.api.boundary_models import (
    MAX_BINARY_SIZE,
    MAX_COUNT,
    SafeRelativePosixPath,
)
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
    discovered_roots: int = Field(ge=0, le=MAX_COUNT)
    observed_files: int = Field(ge=0, le=MAX_COUNT)
    local_files: int = Field(ge=0, le=MAX_COUNT)
    placeholder_files: int = Field(ge=0, le=MAX_COUNT)
    proposed_files: int = Field(ge=0, le=MAX_COUNT)
    last_event_sequence: int = Field(ge=0, le=MAX_COUNT)
    current_root_id: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=_SHA256,
    )
    current_relative_path: SafeRelativePosixPath | None = None
    last_error: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def has_consistent_counts(self) -> OrganizerStatusResponse:
        if self.local_files + self.placeholder_files > self.observed_files:
            raise ValueError(
                "local and placeholder files cannot exceed observed files"
            )
        if self.proposed_files > self.observed_files:
            raise ValueError("proposed files cannot exceed observed files")
        if (self.current_root_id is None) is not (
            self.current_relative_path is None
        ):
            raise ValueError(
                "current root and relative path must be present together"
            )
        return self


class OrganizerProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    file_id: str = Field(
        min_length=64,
        max_length=64,
        pattern=_SHA256,
    )
    root_id: str = Field(
        min_length=64,
        max_length=64,
        pattern=_SHA256,
    )
    relative_path: SafeRelativePosixPath
    name: str = Field(min_length=1, max_length=1024)
    extension: str = Field(
        max_length=128, pattern=r"^(|\.[^/\\\x00-\x1f\x7f]+)$"
    )
    byte_size: int = Field(ge=0, le=MAX_BINARY_SIZE)
    availability: OrganizerFileAvailability
    para_category: OrganizerParaCategory
    life_domain: LifeDomain
    course_code: CourseCode | None
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    suggested_group: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)
    model_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=_SHA256,
    )
    proposed_at: datetime

    @model_validator(mode="after")
    def has_consistent_display_identity(self) -> OrganizerProposalResponse:
        if self.relative_path.rsplit("/", maxsplit=1)[-1] != self.name:
            raise ValueError("proposal name must match its relative path")
        if self.extension and not self.name.endswith(self.extension):
            raise ValueError("proposal extension must match its name")
        return self


class OrganizerProposalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: tuple[OrganizerProposalResponse, ...] = Field(max_length=500)
    total: int = Field(ge=0, le=MAX_COUNT)
    complete: bool

    @model_validator(mode="after")
    def has_consistent_completion(self) -> OrganizerProposalListResponse:
        if self.total < len(self.proposals):
            raise ValueError("proposal total cannot be smaller than the page")
        if self.complete is not (len(self.proposals) == self.total):
            raise ValueError("proposal completion must match the bounded page")
        file_ids = [proposal.file_id for proposal in self.proposals]
        paths = [
            (proposal.root_id, proposal.relative_path)
            for proposal in self.proposals
        ]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("proposal file ids must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("proposal root/path identities must be unique")
        return self
