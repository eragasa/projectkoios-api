import json
from pathlib import Path

import pytest
from projectkoios.api.publications import (
    PublicationCatalogError,
    PublicationRepository,
)


def test__list_publications__empty_without_path() -> None:
    repository = PublicationRepository(None)

    catalog = repository.list_publications()

    assert catalog.schema_version == "1"
    assert catalog.publications == ()


def test__list_publications__loads_valid_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "publications.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "publications": [
                    {
                        "id": "software.example-1",
                        "slug": "example-1",
                        "kind": "software",
                        "title": "Example software",
                        "summary": "A bounded public record.",
                        "authors": ["Project Koios"],
                        "published_on": "2026-09-22",
                        "version": "1.0.0",
                        "claims": ["The record has passed software checks."],
                        "limitations": ["No scientific validation is claimed."],
                        "links": [
                            {
                                "label": "Repository",
                                "url": "https://example.test/repository",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    catalog = PublicationRepository(catalog_path).list_publications()

    assert len(catalog.publications) == 1
    publication = catalog.publications[0]
    assert publication.id == "software.example-1"
    assert publication.version == "1.0.0"
    assert str(publication.links[0].url) == "https://example.test/repository"


@pytest.mark.parametrize(
    "document",
    [
        "not-json",
        json.dumps({"schema_version": "2", "publications": []}),
        json.dumps(
            {
                "schema_version": "1",
                "publications": [
                    {
                        "id": "duplicate",
                        "slug": "one",
                        "kind": "report",
                        "title": "First",
                        "summary": "First record",
                        "authors": ["Author"],
                        "published_on": "2026-09-22",
                    },
                    {
                        "id": "duplicate",
                        "slug": "two",
                        "kind": "report",
                        "title": "Second",
                        "summary": "Second record",
                        "authors": ["Author"],
                        "published_on": "2026-09-22",
                    },
                ],
            }
        ),
    ],
)
def test__initialization__rejects_invalid_catalog(
    tmp_path: Path,
    document: str,
) -> None:
    catalog_path = tmp_path / "publications.json"
    catalog_path.write_text(document, encoding="utf-8")

    with pytest.raises(PublicationCatalogError):
        PublicationRepository(catalog_path)
