from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.organizer_models import (
    LifeDomain,
    OrganizerActivity,
    OrganizerControlMode,
    OrganizerProposalListResponse,
    OrganizerProposalResponse,
    OrganizerStatusResponse,
)
from projectkoios.api.provider_errors import ProviderUnavailable
from projectkoios.api.routers.organizer import create_organizer_router


def _status(
    mode: OrganizerControlMode = OrganizerControlMode.OFF,
) -> OrganizerStatusResponse:
    return OrganizerStatusResponse(
        desired_mode=mode,
        activity=OrganizerActivity.OFF,
        discovered_roots=1,
        observed_files=2,
        local_files=2,
        placeholder_files=0,
        proposed_files=1,
        last_event_sequence=7,
        current_root_id=None,
        current_relative_path=None,
        last_error=None,
    )


def _proposal() -> OrganizerProposalResponse:
    return OrganizerProposalResponse(
        file_id="1" * 64,
        root_id="2" * 64,
        relative_path="Courses/ENGR219/example.m",
        name="example.m",
        extension=".m",
        byte_size=128,
        availability="local",
        para_category="resource",
        life_domain="teaching",
        course_code="ENGR219",
        confidence=0.9,
        suggested_group="Homework",
        rationale="The owner projected this course identity.",
        model="fixture",
        model_digest="3" * 64,
        proposed_at=datetime(2026, 9, 27, tzinfo=UTC),
    )


class _OrganizerFixture:
    def __init__(self) -> None:
        self.proposal_calls: list[tuple[LifeDomain, int]] = []
        self.control_calls: list[OrganizerControlMode] = []

    def read_status(self) -> OrganizerStatusResponse:
        return _status()

    def set_control(
        self,
        mode: OrganizerControlMode,
    ) -> OrganizerStatusResponse:
        self.control_calls.append(mode)
        return _status(mode)

    def list_proposals(
        self,
        *,
        life_domain: LifeDomain,
        limit: int,
    ) -> OrganizerProposalListResponse:
        self.proposal_calls.append((life_domain, limit))
        return OrganizerProposalListResponse(
            proposals=(_proposal(),),
            total=1,
            complete=True,
        )


class _UnavailableOrganizer(_OrganizerFixture):
    def read_status(self) -> OrganizerStatusResponse:
        raise ProviderUnavailable


def _client(provider: _OrganizerFixture | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_organizer_router(provider))
    return TestClient(app)


def test__organizer_router__projects_owner_dtos_without_browser_matching() -> (
    None
):
    provider = _OrganizerFixture()
    client = _client(provider)

    status_response = client.get("/organizer/status")
    control_response = client.put(
        "/organizer/control",
        json={"mode": "pause"},
    )
    proposals_response = client.get(
        "/organizer/proposals",
        params={"life_domain": "teaching", "limit": 100},
    )

    assert status_response.status_code == 200
    assert control_response.json()["desired_mode"] == "pause"
    assert proposals_response.json()["proposals"][0]["course_code"] == (
        "ENGR219"
    )
    assert provider.control_calls == [OrganizerControlMode.PAUSE]
    assert provider.proposal_calls == [(LifeDomain.TEACHING, 100)]


@pytest.mark.parametrize(
    ("path", "parameters"),
    [
        ("/organizer/proposals", {"limit": 0}),
        ("/organizer/proposals", {"limit": 501}),
    ],
)
def test__organizer_router__rejects_out_of_bounds_queries(
    path: str,
    parameters: dict[str, int],
) -> None:
    provider = _OrganizerFixture()

    response = _client(provider).get(path, params=parameters)

    assert response.status_code == 422
    assert provider.proposal_calls == []


def test__organizer_router__is_honestly_unavailable_without_owner() -> None:
    client = _client(None)

    responses = [
        client.get("/organizer/status"),
        client.put("/organizer/control", json={"mode": "off"}),
        client.get("/organizer/proposals"),
    ]

    assert all(response.status_code == 503 for response in responses)
    assert all(
        response.json() == {"detail": "organizer provider is unavailable"}
        for response in responses
    )


def test__organizer_router__maps_owner_unavailability_to_safe_error() -> None:
    response = _client(_UnavailableOrganizer()).get("/organizer/status")

    assert response.status_code == 503
    assert response.json() == {"detail": "organizer provider is unavailable"}


@pytest.mark.parametrize(
    "path",
    ["/organizer/events", "/organizer/events/stream"],
)
def test__organizer_router__does_not_expose_underspecified_events(
    path: str,
) -> None:
    response = _client(_OrganizerFixture()).get(path)

    assert response.status_code == 404
