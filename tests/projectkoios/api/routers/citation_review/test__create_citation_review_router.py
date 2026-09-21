from __future__ import annotations

import asyncio
import json
import sqlite3
import stat
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from projectkoios.api.citation_review import CitationReviewRepository
from projectkoios.api.routers.citation_review import (
    create_citation_review_router,
)


def _bundle(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "assessment": "AI_REVIEWED_UNVERIFIED",
                "manuscript_sha256": "a" * 64,
                "items": [
                    {
                        "claim_id": "claim-001",
                        "lines": "10-12",
                        "claim": "A claim requiring a citation.",
                        "query": "claim citation",
                        "manuscript_excerpt_latex": "Energy is $E=mc^2$.",
                        "manuscript_equations": [
                            {"latex": "E=mc^2", "display": False}
                        ],
                        "expected_keys": ["source2024"],
                        "expected_keys_available": ["source2024"],
                        "expected_outcome": "candidate_source",
                        "evaluation_status": "HIT",
                        "recommendation_relationship": "DIRECT_SUPPORT",
                        "recommended_keys": ["source2024"],
                        "recommendation": "Inspect the displayed passage.",
                        "candidates": [
                            {
                                "rank": 1,
                                "citation_key": "source2024",
                                "bibtex_entry_present": True,
                                "score": 4.5,
                                "file": "source2024.pdf",
                                "physical_page": 3,
                                "printed_page": "2",
                                "passage_id": "passage:1",
                                "passage": "Evidence for the claim.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def configured_app(tmp_path: Path) -> tuple[FastAPI, Path]:
    bundle = tmp_path / "bundle.json"
    decisions = tmp_path / "decisions.sqlite3"
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "source2024.pdf").write_bytes(b"%PDF-1.4 test")
    _bundle(bundle)
    application = FastAPI()
    application.include_router(
        create_citation_review_router(
            CitationReviewRepository(bundle, decisions, sources)
        )
    )
    return application, decisions


def _request(
    app: FastAPI,
    method: str,
    path: str,
    json_body: dict[str, object] | None = None,
) -> httpx2.Response:
    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.request(method, path, json=json_body)

    return asyncio.run(send())


def test__queue__returns_review_progress(
    configured_app: tuple[FastAPI, Path],
) -> None:
    app, _ = configured_app

    response = _request(app, "GET", "/citation-reviews")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["decided"] == 0
    assert response.json()["items"][0]["claim_id"] == "claim-001"

    detail = _request(app, "GET", "/citation-reviews/claim-001")
    assert detail.json()["manuscript_equations"] == [
        {"latex": "E=mc^2", "display": False}
    ]


def test__source__serves_only_bundle_source(
    configured_app: tuple[FastAPI, Path],
) -> None:
    app, _ = configured_app

    response = _request(
        app,
        "GET",
        "/citation-reviews/sources/source2024.pdf",
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test__decide__persists_private_revisioned_decision(
    configured_app: tuple[FastAPI, Path],
) -> None:
    app, decisions = configured_app

    response = _request(
        app,
        "PUT",
        "/citation-reviews/claim-001/decision",
        {
            "disposition": "ACCEPT_CITATION",
            "selected_citation_keys": ["source2024"],
            "note": "Checked the displayed passage.",
        },
    )
    revised = _request(
        app,
        "PUT",
        "/citation-reviews/claim-001/decision",
        {
            "disposition": "PARTIAL_SUPPORT",
            "selected_citation_keys": ["source2024"],
            "note": "Second review pass.",
        },
    )
    queue = _request(app, "GET", "/citation-reviews")

    assert response.status_code == 200
    assert response.json()["revision"] == 1
    assert revised.json()["revision"] == 2
    assert queue.json()["decided"] == 1
    assert queue.json()["items"][0]["decision"]["disposition"] == (
        "PARTIAL_SUPPORT"
    )
    with sqlite3.connect(decisions) as connection:
        revision_count = connection.execute(
            "SELECT COUNT(*) FROM citation_decisions"
        ).fetchone()[0]
    assert revision_count == 2
    assert stat.S_IMODE(decisions.stat().st_mode) == 0o600


def test__queue__does_not_reuse_decision_for_another_manuscript(
    configured_app: tuple[FastAPI, Path],
) -> None:
    app, decisions = configured_app
    _request(
        app,
        "PUT",
        "/citation-reviews/claim-001/decision",
        {
            "disposition": "CORPUS_GAP",
            "selected_citation_keys": [],
            "note": "",
        },
    )
    bundle = decisions.parent / "bundle.json"
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["manuscript_sha256"] = "b" * 64
    bundle.write_text(json.dumps(payload), encoding="utf-8")

    response = _request(app, "GET", "/citation-reviews")

    assert response.status_code == 200
    assert response.json()["decided"] == 0
    assert response.json()["items"][0]["decision"] is None


def test__decide__rejects_acceptance_without_selected_source(
    configured_app: tuple[FastAPI, Path],
) -> None:
    app, _ = configured_app

    response = _request(
        app,
        "PUT",
        "/citation-reviews/claim-001/decision",
        {
            "disposition": "ACCEPT_CITATION",
            "selected_citation_keys": [],
            "note": "",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "this disposition requires at least one selected citation"
    )
