from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    RootModel,
    model_validator,
)

_IDENTIFIER = r"^[a-z0-9][a-z0-9._-]{0,127}$"
_COURSE_CODE = r"^[A-Z0-9-]{2,32}$"
_REPOSITORY = r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
CatalogNote = Annotated[str, Field(min_length=1, max_length=500)]


class CourseCode(RootModel[str]):
    """Nominal nullable course identity supplied by an owning adapter."""

    root: str = Field(
        min_length=2,
        max_length=32,
        pattern=_COURSE_CODE,
    )


class CourseMaterialsStatus(StrEnum):
    INVENTORY_ONLY = "inventory-only"
    REVIEW_CANDIDATE = "review-candidate"
    PUBLISHED = "published"


class PublicCourseSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(
        min_length=3,
        max_length=201,
        pattern=_REPOSITORY,
    )
    revision: str = Field(
        min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$"
    )
    url: HttpUrl


class PublicCourseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER)
    code: CourseCode
    title: str | None = Field(default=None, min_length=1, max_length=240)
    materials_status: CourseMaterialsStatus


class PublicCourseInstitution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER)
    name: str = Field(min_length=1, max_length=200)
    courses: tuple[PublicCourseRecord, ...] = Field(
        min_length=1,
        max_length=200,
    )

    @model_validator(mode="after")
    def course_identities_match_institution(self) -> PublicCourseInstitution:
        expected_prefix = f"{self.id}."
        identifiers = [course.id for course in self.courses]
        codes = [course.code.root for course in self.courses]
        if any(
            not identifier.startswith(expected_prefix)
            for identifier in identifiers
        ):
            raise ValueError(
                "course ids must use their institution id as a prefix"
            )
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("course ids must be unique within an institution")
        if len(codes) != len(set(codes)):
            raise ValueError(
                "course codes must be unique within an institution"
            )
        return self


class PublicCourseCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    reviewed_on: date | None = None
    source: PublicCourseSource | None = None
    publication_boundary: tuple[CatalogNote, ...] = Field(
        default=(),
        max_length=20,
    )
    institutions: tuple[PublicCourseInstitution, ...] = Field(
        default=(),
        max_length=50,
    )
    unresolved_collections: tuple[CatalogNote, ...] = Field(
        default=(),
        max_length=30,
    )

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
        if len(self.publication_boundary) != len(
            set(self.publication_boundary)
        ):
            raise ValueError("publication boundary entries must be unique")
        if len(self.unresolved_collections) != len(
            set(self.unresolved_collections)
        ):
            raise ValueError("unresolved collection entries must be unique")
        return self
