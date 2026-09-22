from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

_IDENTIFIER = r"^[a-z0-9][a-z0-9._-]{0,127}$"


class CourseMaterialsStatus(StrEnum):
    INVENTORY_ONLY = "inventory-only"
    REVIEW_CANDIDATE = "review-candidate"
    PUBLISHED = "published"


class PublicCourseSource(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    url: HttpUrl


class PublicCourseRecord(BaseModel):
    id: str = Field(pattern=_IDENTIFIER)
    code: str = Field(pattern=r"^[A-Z0-9-]{2,32}$")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    materials_status: CourseMaterialsStatus


class PublicCourseInstitution(BaseModel):
    id: str = Field(pattern=_IDENTIFIER)
    name: str = Field(min_length=1, max_length=200)
    courses: tuple[PublicCourseRecord, ...] = Field(
        min_length=1, max_length=200
    )

    @model_validator(mode="after")
    def course_identities_match_institution(self) -> PublicCourseInstitution:
        expected_prefix = f"{self.id}."
        identifiers = [course.id for course in self.courses]
        if any(
            not identifier.startswith(expected_prefix)
            for identifier in identifiers
        ):
            raise ValueError(
                "course ids must use their institution id as a prefix"
            )
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("course ids must be unique within an institution")
        return self


class PublicCourseCatalog(BaseModel):
    schema_version: Literal["1"] = "1"
    reviewed_on: date | None = None
    source: PublicCourseSource | None = None
    publication_boundary: tuple[str, ...] = Field(default=(), max_length=20)
    institutions: tuple[PublicCourseInstitution, ...] = Field(
        default=(), max_length=50
    )
    unresolved_collections: tuple[str, ...] = Field(default=(), max_length=30)

    @model_validator(mode="after")
    def catalog_identities_are_unique(self) -> PublicCourseCatalog:
        if self.institutions and (
            self.reviewed_on is None
            or self.source is None
            or not self.publication_boundary
        ):
            raise ValueError(
                "nonempty course catalogs require review, source, and boundary"
            )
        if not self.institutions and (
            self.reviewed_on is not None
            or self.source is not None
            or self.publication_boundary
            or self.unresolved_collections
        ):
            raise ValueError(
                "empty course catalogs cannot declare review metadata"
            )
        institution_ids = [institution.id for institution in self.institutions]
        if len(institution_ids) != len(set(institution_ids)):
            raise ValueError("institution ids must be unique")
        course_ids = [
            course.id
            for institution in self.institutions
            for course in institution.courses
        ]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("course ids must be unique")
        return self
