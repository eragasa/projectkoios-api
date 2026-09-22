from __future__ import annotations

import json
from pathlib import Path

from projectkoios.api.publication_models import PublicationCatalog
from pydantic import ValidationError


class PublicationCatalogError(RuntimeError):
    """Raised when configured public publication data cannot be loaded."""


class PublicationRepository:
    """Immutable public publication catalog loaded at application startup."""

    def __init__(self, catalog_path: Path | None) -> None:
        self.catalog_path = catalog_path
        self._catalog = self._load(catalog_path)

    def list_publications(self) -> PublicationCatalog:
        return self._catalog

    @staticmethod
    def _load(catalog_path: Path | None) -> PublicationCatalog:
        if catalog_path is None:
            return PublicationCatalog()

        try:
            document = json.loads(catalog_path.read_text(encoding="utf-8"))
            return PublicationCatalog.model_validate(document)
        except OSError as error:
            raise PublicationCatalogError(
                f"cannot read publication catalog: {catalog_path}"
            ) from error
        except (json.JSONDecodeError, ValidationError) as error:
            raise PublicationCatalogError(
                f"invalid publication catalog: {catalog_path}"
            ) from error
