from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.agent.organizer import (
    CategorizationProposal,
    CloudRoot,
    FileAvailability,
    FileObservation,
    LifeDomain,
    OrganizerCatalog,
    ParaCategory,
)
from projectkoios.api.routers.organizer import create_organizer_router


def test__organizer_router__reports_status_and_accepts_control(
    tmp_path: Path,
) -> None:
    catalog = OrganizerCatalog(tmp_path / "catalog.sqlite3")
    app = FastAPI()
    app.include_router(create_organizer_router(catalog))
    client = TestClient(app)

    initial = client.get("/organizer/status")
    enabled = client.put("/organizer/control", json={"mode": "on"})
    events = client.get("/organizer/events", params={"after": 0})

    assert initial.status_code == 200
    assert initial.json()["desired_mode"] == "off"
    assert enabled.status_code == 200
    assert enabled.json()["desired_mode"] == "on"
    assert events.status_code == 200
    assert events.json()["events"][0]["kind"] == "control"


def test__organizer_router__returns_bounded_teaching_proposals(
    tmp_path: Path,
) -> None:
    catalog = OrganizerCatalog(tmp_path / "catalog.sqlite3")
    root = CloudRoot("1" * 64, "Course files", tmp_path, "fixture")
    observation = FileObservation(
        file_id="2" * 64,
        root_id=root.root_id,
        relative_path="Courses/ENGR219/Homework/example.m",
        name="example.m",
        extension=".m",
        byte_size=128,
        modified_ns=1,
        availability=FileAvailability.LOCAL,
    )
    catalog.record_root(root)
    catalog.record_file(observation)
    catalog.record_proposal(
        CategorizationProposal(
            file_id=observation.file_id,
            para_category=ParaCategory.RESOURCE,
            life_domain=LifeDomain.TEACHING,
            confidence=0.9,
            suggested_group="ENGR219",
            rationale="The path names a known course code.",
            model="fixture",
            model_digest="3" * 64,
        )
    )
    app = FastAPI()
    app.include_router(create_organizer_router(catalog))
    client = TestClient(app)

    response = client.get(
        "/organizer/proposals",
        params={"life_domain": "teaching", "limit": 20},
    )

    assert response.status_code == 200
    assert response.json() == {
        "proposals": [
            {
                "file_id": "2" * 64,
                "root_id": "1" * 64,
                "relative_path": "Courses/ENGR219/Homework/example.m",
                "name": "example.m",
                "extension": ".m",
                "byte_size": 128,
                "availability": "local",
                "para_category": "resource",
                "life_domain": "teaching",
                "confidence": 0.9,
                "suggested_group": "ENGR219",
                "rationale": "The path names a known course code.",
                "model": "fixture",
                "model_digest": "3" * 64,
                "proposed_at": response.json()["proposals"][0]["proposed_at"],
            }
        ],
        "total": 1,
        "complete": True,
    }


def test__organizer_router__rejects_unknown_control_mode(
    tmp_path: Path,
) -> None:
    catalog = OrganizerCatalog(tmp_path / "catalog.sqlite3")
    app = FastAPI()
    app.include_router(create_organizer_router(catalog))
    client = TestClient(app)

    response = client.put("/organizer/control", json={"mode": "delete"})

    assert response.status_code == 422
    assert catalog.status().desired_mode.value == "off"
