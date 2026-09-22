from __future__ import annotations

import json
from pathlib import Path

from projectkoios.api.project_models import PublicProjectCatalog
from pydantic import ValidationError


class PublicProjectCatalogError(RuntimeError):
    """Raised when configured public project data cannot be loaded."""


class PublicProjectRepository:
    """Immutable public project catalog loaded at application startup."""

    def __init__(self, catalog_path: Path | None) -> None:
        self.catalog_path = catalog_path
        self._catalog = self._load(catalog_path)

    def list_projects(self) -> PublicProjectCatalog:
        return self._catalog

    @staticmethod
    def _load(catalog_path: Path | None) -> PublicProjectCatalog:
        if catalog_path is None:
            return PublicProjectCatalog(
                schema_version="1",
                projects=(),
            )

        try:
            document = json.loads(
                catalog_path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_fields,
            )
            return PublicProjectCatalog.model_validate(document)
        except OSError as error:
            raise PublicProjectCatalogError(
                f"cannot read public project catalog: {catalog_path}"
            ) from error
        except (json.JSONDecodeError, ValueError, ValidationError) as error:
            raise PublicProjectCatalogError(
                f"invalid public project catalog: {catalog_path}"
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
