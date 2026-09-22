from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

_IDENTIFIER = r"^[a-z0-9][a-z0-9._-]{0,127}$"


class PublicationKind(StrEnum):
    SOFTWARE = "software"
    ARTICLE = "article"
    DATASET = "dataset"
    REPORT = "report"


class PublicationLink(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    url: HttpUrl


class PublicationRecord(BaseModel):
    id: str = Field(pattern=_IDENTIFIER)
    slug: str = Field(pattern=_IDENTIFIER)
    kind: PublicationKind
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=2000)
    authors: tuple[str, ...] = Field(min_length=1)
    published_on: date
    version: str | None = Field(default=None, max_length=80)
    citation: str | None = Field(default=None, max_length=4000)
    topics: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    links: tuple[PublicationLink, ...] = ()


class PublicationCatalog(BaseModel):
    schema_version: Literal["1"] = "1"
    publications: tuple[PublicationRecord, ...] = ()

    @model_validator(mode="after")
    def publication_identities_are_unique(self) -> PublicationCatalog:
        identifiers = [publication.id for publication in self.publications]
        slugs = [publication.slug for publication in self.publications]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("publication ids must be unique")
        if len(slugs) != len(set(slugs)):
            raise ValueError("publication slugs must be unique")
        return self
