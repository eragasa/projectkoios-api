from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

_IDENTIFIER = r"^[a-z0-9][a-z0-9._-]{0,127}$"


class PublicProjectStatus(StrEnum):
    ACTIVE_DEVELOPMENT = "active-development"
    MAINTAINED = "maintained"
    ARCHIVED = "archived"


class PublicCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    IN_DEVELOPMENT = "in-development"
    PLANNED = "planned"


class PublicProjectCapability(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    status: PublicCapabilityStatus
    summary: str = Field(min_length=1, max_length=1000)


class PublicProjectLink(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    url: HttpUrl


class PublicProjectRecord(BaseModel):
    id: str = Field(pattern=_IDENTIFIER)
    slug: str = Field(pattern=_IDENTIFIER)
    name: str = Field(min_length=1, max_length=160)
    tagline: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=3000)
    status: PublicProjectStatus
    topics: tuple[str, ...] = Field(default=(), max_length=20)
    purposes: tuple[str, ...] = Field(default=(), min_length=1, max_length=20)
    principles: tuple[str, ...] = Field(default=(), max_length=20)
    capabilities: tuple[PublicProjectCapability, ...] = Field(
        default=(), max_length=30
    )
    limitations: tuple[str, ...] = Field(default=(), max_length=20)
    links: tuple[PublicProjectLink, ...] = Field(default=(), max_length=20)


class PublicProjectCatalog(BaseModel):
    schema_version: Literal["1"] = "1"
    projects: tuple[PublicProjectRecord, ...] = ()

    @model_validator(mode="after")
    def project_identities_are_unique(self) -> PublicProjectCatalog:
        identifiers = [project.id for project in self.projects]
        slugs = [project.slug for project in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("project ids must be unique")
        if len(slugs) != len(set(slugs)):
            raise ValueError("project slugs must be unique")
        return self
