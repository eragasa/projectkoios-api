import json
from pathlib import Path

import pytest
from projectkoios.api.courses import (
    PublicCourseCatalogError,
    PublicCourseRepository,
)


def _catalog_document() -> dict[str, object]:
    return {
        "schema_version": "1",
        "reviewed_on": "2026-09-22",
        "source": {
            "repository": "eragasa/projectkoios-courses",
            "revision": "7bd6ce797d10381d436b89dbc12b226a95719d42",
            "url": (
                "https://github.com/eragasa/projectkoios-courses/blob/"
                "7bd6ce797d10381d436b89dbc12b226a95719d42/"
                "docs/migration/course-source-inventory.md"
            ),
        },
        "publication_boundary": ["Course identity only."],
        "institutions": [
            {
                "id": "pacific",
                "name": "University of the Pacific",
                "courses": [
                    {
                        "id": "pacific.engr219",
                        "code": "ENGR219",
                        "title": "Numerical Methods for Engineering",
                        "materials_status": "review-candidate",
                    }
                ],
            }
        ],
        "unresolved_collections": ["Unassigned historical material."],
    }


def test__list_courses__returns_empty_catalog_without_path() -> None:
    catalog = PublicCourseRepository(None).list_courses()

    assert catalog.schema_version == "1"
    assert catalog.reviewed_on is None
    assert catalog.source is None
    assert catalog.institutions == ()


def test__list_courses__loads_public_safe_metadata(tmp_path: Path) -> None:
    catalog_path = tmp_path / "courses.json"
    catalog_path.write_text(json.dumps(_catalog_document()), encoding="utf-8")

    catalog = PublicCourseRepository(catalog_path).list_courses()

    assert catalog.reviewed_on is not None
    assert catalog.source is not None
    assert catalog.source.revision == (
        "7bd6ce797d10381d436b89dbc12b226a95719d42"
    )
    assert catalog.institutions[0].courses[0].materials_status == (
        "review-candidate"
    )


@pytest.mark.parametrize(
    "document",
    [
        "not-json",
        '{"schema_version":"1","schema_version":"1"}',
        json.dumps(
            {
                "schema_version": "1",
                "reviewed_on": "2026-09-22",
                "institutions": [],
            }
        ),
        json.dumps(
            {
                **_catalog_document(),
                "institutions": [
                    {
                        "id": "pacific",
                        "name": "University of the Pacific",
                        "courses": [
                            {
                                "id": "uf.ema6114",
                                "code": "EMA6114",
                                "title": None,
                                "materials_status": "inventory-only",
                            }
                        ],
                    }
                ],
            }
        ),
    ],
)
def test__initialization__rejects_invalid_catalog(
    tmp_path: Path,
    document: str,
) -> None:
    catalog_path = tmp_path / "courses.json"
    catalog_path.write_text(document, encoding="utf-8")

    with pytest.raises(PublicCourseCatalogError):
        PublicCourseRepository(catalog_path)
