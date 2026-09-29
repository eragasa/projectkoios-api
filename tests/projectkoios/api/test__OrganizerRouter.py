from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.agent.organizer import OrganizerCatalog
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
