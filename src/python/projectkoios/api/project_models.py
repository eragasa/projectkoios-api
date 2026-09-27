from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

_IDENTIFIER = r"^[a-z0-9][a-z0-9._-]{0,127}$"
_REPOSITORY = r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
Topic = Annotated[str, Field(min_length=1, max_length=160)]
Statement = Annotated[str, Field(min_length=1, max_length=1000)]


class PublicProjectStatus(StrEnum):
    ACTIVE_DEVELOPMENT = "active-development"
    MAINTAINED = "maintained"
    ARCHIVED = "archived"


class PublicCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    IN_DEVELOPMENT = "in-development"
    PLANNED = "planned"


class PublicProjectCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    status: PublicCapabilityStatus
    summary: str = Field(min_length=1, max_length=1000)


class PublicProjectLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    url: HttpUrl


class PublicProjectReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_version: str = Field(
        min_length=5,
        max_length=32,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )
    reviewed_on: date
    review_url: HttpUrl


class PublicProjectSourceRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(
        min_length=3,
        max_length=201,
        pattern=_REPOSITORY,
    )
    revision: str = Field(
        min_length=40,
        max_length=40,
        pattern=r"^[0-9a-f]{40}$",
    )
    url: HttpUrl


class PublicProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER)
    slug: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER)
    name: str = Field(min_length=1, max_length=160)
    tagline: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=3000)
    status: PublicProjectStatus
    review: PublicProjectReview
    source_revisions: tuple[PublicProjectSourceRevision, ...] = Field(
        min_length=1,
        max_length=20,
    )
    evidence: tuple[PublicProjectLink, ...] = Field(
        min_length=1,
        max_length=30,
    )
    topics: tuple[Topic, ...] = Field(default=(), max_length=20)
    purposes: tuple[Statement, ...] = Field(
        default=(),
        min_length=1,
        max_length=20,
    )
    principles: tuple[Statement, ...] = Field(default=(), max_length=20)
    capabilities: tuple[PublicProjectCapability, ...] = Field(
        default=(),
        max_length=30,
    )
    limitations: tuple[Statement, ...] = Field(default=(), max_length=20)
    links: tuple[PublicProjectLink, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def collection_identities_are_unique(self) -> PublicProjectRecord:
        repositories = [source.repository for source in self.source_revisions]
        if len(repositories) != len(set(repositories)):
            raise ValueError("source revision repositories must be unique")
        for name, statement_values in (
            ("topics", self.topics),
            ("purposes", self.purposes),
            ("principles", self.principles),
            ("limitations", self.limitations),
        ):
            if len(statement_values) != len(set(statement_values)):
                raise ValueError(f"project {name} must be unique")
        capability_names = [value.name for value in self.capabilities]
        if len(capability_names) != len(set(capability_names)):
            raise ValueError("project capability names must be unique")
        for name, link_values in (
            ("evidence", self.evidence),
            ("links", self.links),
        ):
            labels = [value.label for value in link_values]
            identities = [
                (value.label, str(value.url)) for value in link_values
            ]
            if len(labels) != len(set(labels)) or len(identities) != len(
                set(identities)
            ):
                raise ValueError(f"project {name} identities must be unique")
        return self


class PublicProjectCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    projects: tuple[PublicProjectRecord, ...] = Field(
        default=(),
        max_length=200,
    )

    @model_validator(mode="after")
    def project_identities_are_unique(self) -> PublicProjectCatalog:
        identifiers = [project.id for project in self.projects]
        slugs = [project.slug for project in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("project ids must be unique")
        if len(slugs) != len(set(slugs)):
            raise ValueError("project slugs must be unique")
        return self
