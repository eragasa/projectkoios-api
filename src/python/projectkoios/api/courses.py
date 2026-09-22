from __future__ import annotations

import json
from pathlib import Path

from projectkoios.api.course_models import PublicCourseCatalog
from pydantic import ValidationError


class PublicCourseCatalogError(RuntimeError):
    """Raised when configured public course metadata cannot be loaded."""


class PublicCourseRepository:
    """Immutable public-safe course catalog loaded at application startup."""

    def __init__(self, catalog_path: Path | None) -> None:
        self.catalog_path = catalog_path
        self._catalog = self._load(catalog_path)

    def list_courses(self) -> PublicCourseCatalog:
        return self._catalog

    @staticmethod
    def _load(catalog_path: Path | None) -> PublicCourseCatalog:
        if catalog_path is None:
            return PublicCourseCatalog(schema_version="1")

        try:
            document = json.loads(
                catalog_path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_fields,
            )
            return PublicCourseCatalog.model_validate(document)
        except OSError as error:
            raise PublicCourseCatalogError(
                f"cannot read public course catalog: {catalog_path}"
            ) from error
        except (json.JSONDecodeError, ValueError, ValidationError) as error:
            raise PublicCourseCatalogError(
                f"invalid public course catalog: {catalog_path}"
            ) from error


def _reject_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result
