import json
from pathlib import Path

import pytest
from projectkoios.api.projects import (
    PublicProjectCatalogError,
    PublicProjectRepository,
)


def _project_record() -> dict[str, object]:
    return {
        "id": "projectkoios",
        "slug": "projectkoios",
        "name": "Project Koios",
        "tagline": "Evidence-connected scientific work.",
        "summary": "A bounded public project overview.",
        "status": "active-development",
        "topics": ["research software"],
        "purposes": ["Connect technical work to its evidence."],
        "principles": ["Preserve explicit provenance."],
        "capabilities": [
            {
                "name": "Public publishing",
                "status": "available",
                "summary": "Display explicitly approved public records.",
            }
        ],
        "limitations": ["No scientific validation is implied."],
        "links": [
            {
                "label": "Repository",
                "url": "https://github.com/eragasa/projectkoios",
            }
        ],
    }


def test__list_projects__returns_empty_catalog_without_path() -> None:
    catalog = PublicProjectRepository(None).list_projects()

    assert catalog.schema_version == "1"
    assert catalog.projects == ()


def test__list_projects__loads_bounded_public_project(tmp_path: Path) -> None:
    catalog_path = tmp_path / "projects.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "projects": [_project_record()],
            }
        ),
        encoding="utf-8",
    )

    catalog = PublicProjectRepository(catalog_path).list_projects()

    assert len(catalog.projects) == 1
    assert catalog.projects[0].id == "projectkoios"
    assert catalog.projects[0].capabilities[0].status == "available"


@pytest.mark.parametrize(
    "document",
    [
        "not-json",
        json.dumps(
            {
                "schema_version": "2",
                "projects": [],
            }
        ),
        '{"schema_version":"1","schema_version":"1","projects":[]}',
        json.dumps(
            {
                "schema_version": "1",
                "projects": [_project_record(), _project_record()],
            }
        ),
    ],
)
def test__initialization__rejects_invalid_catalog(
    tmp_path: Path,
    document: str,
) -> None:
    catalog_path = tmp_path / "projects.json"
    catalog_path.write_text(document, encoding="utf-8")

    with pytest.raises(PublicProjectCatalogError):
        PublicProjectRepository(catalog_path)
