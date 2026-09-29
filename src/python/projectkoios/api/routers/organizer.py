from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from projectkoios.agent.organizer import (
    OrganizerControlMode,
    OrganizerEvent,
    OrganizerStatus,
)
from projectkoios.api.organizer_models import (
    OrganizerControlRequest,
    OrganizerEventListResponse,
    OrganizerEventResponse,
    OrganizerStatusResponse,
)


class OrganizerProvider(Protocol):
    def set_mode(self, mode: OrganizerControlMode) -> None: ...

    def status(self) -> OrganizerStatus: ...

    def events_after(
        self, sequence: int, limit: int = 200
    ) -> tuple[OrganizerEvent, ...]: ...


def create_organizer_router(provider: OrganizerProvider) -> APIRouter:
    router = APIRouter(prefix="/organizer", tags=["organizer"])

    @router.get("/status", response_model=OrganizerStatusResponse)
    def read_status() -> OrganizerStatusResponse:
        return _status_response(provider.status())

    @router.put("/control", response_model=OrganizerStatusResponse)
    def update_control(
        request: OrganizerControlRequest,
    ) -> OrganizerStatusResponse:
        provider.set_mode(OrganizerControlMode(request.mode))
        return _status_response(provider.status())

    @router.get("/events", response_model=OrganizerEventListResponse)
    def read_events(
        after: int = Query(default=0, ge=0),
    ) -> OrganizerEventListResponse:
        return OrganizerEventListResponse(
            events=[
                _event_response(value) for value in provider.events_after(after)
            ]
        )

    @router.get("/events/stream", response_class=StreamingResponse)
    def stream_events(
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(provider, request, after),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router


async def _event_stream(
    provider: OrganizerProvider,
    request: Request,
    after: int,
) -> AsyncIterator[str]:
    sequence = after
    while not await request.is_disconnected():
        events = provider.events_after(sequence)
        if events:
            for event in events:
                sequence = event.sequence
                payload = _event_response(event).model_dump(mode="json")
                yield (
                    f"id: {event.sequence}\n"
                    f"event: organizer\n"
                    f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                )
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(1.0)


def _status_response(status: OrganizerStatus) -> OrganizerStatusResponse:
    return OrganizerStatusResponse(
        desired_mode=status.desired_mode.value,
        activity=status.activity.value,
        discovered_roots=status.discovered_roots,
        observed_files=status.observed_files,
        local_files=status.local_files,
        placeholder_files=status.placeholder_files,
        proposed_files=status.proposed_files,
        last_event_sequence=status.last_event_sequence,
        current_root_id=status.current_root_id,
        current_relative_path=status.current_relative_path,
        last_error=status.last_error,
    )


def _event_response(event: OrganizerEvent) -> OrganizerEventResponse:
    return OrganizerEventResponse(
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        kind=event.kind,
        message=event.message,
        root_id=event.root_id,
        file_id=event.file_id,
    )
