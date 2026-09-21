from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

import httpx2
from fastapi import FastAPI
from projectkoios.api.literature_review import LiteratureReviewRepository
from projectkoios.api.routers.literature_review import (
    create_literature_review_router,
)


def _request(
    app: FastAPI,
    path: str,
    *,
    method: str = "GET",
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> httpx2.Response:
    async def send() -> httpx2.Response:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.request(
                method,
                path,
                content=content,
                headers=headers,
                data=data,
                files=files,
            )

    return asyncio.run(send())


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _run(tmp_path: Path, *, assessed: bool) -> Path:
    run = tmp_path / "literature-review-01"
    output = run / "output" / "generation-01"
    evidence = output / "evidence"
    assessments = output / "assessments"
    evidence.mkdir(parents=True)
    assessments.mkdir()
    (run / "intake.md").write_text(
        "# Original framework\n\n$$A = E - TS$$\n",
        encoding="utf-8",
    )
    (run / "claims.jsonl").write_text(
        json.dumps(
            {
                "claim_id": "C-001",
                "section": "method_scope",
                "claim": "The proposed method applies universally.",
                "queries": ["bounded method evidence"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        evidence / "C-001.json",
        {
            "evidence": [
                {
                    "label": "E1",
                    "citation_key": "source2023",
                    "physical_page": 4,
                    "text": "Private retrieved passage.",
                    "locator": "/private/source.pdf",
                }
            ]
        },
    )
    _write_json(
        run / "claim-mathematics.json",
        {
            "assessment_status": "AUTOMATED_UNREVIEWED",
            "items": [
                {
                    "claim_id": "C-001",
                    "finding": "QUALIFIES",
                    "conclusion": "The method scope needs qualification.",
                    "evidence_labels": ["E1"],
                    "equations": [
                        {
                            "label": "Domain",
                            "latex": "0 < x < 1",
                            "interpretation": (
                                "The endpoints are outside the stated domain."
                            ),
                        }
                    ],
                }
            ],
        },
    )
    if assessed:
        _write_json(
            assessments / "C-001.json",
            {
                "claim_id": "C-001",
                "status": "QUALIFIED",
                "summary": "The evidence supports only a bounded scope.",
                "corrected_claim": "The method applies within its domain.",
                "assumptions": ["Stated domain assumptions"],
                "citations": ["E1"],
                "source_requests": [],
            },
        )
        _write_json(
            output / "manifest.json",
            {
                "assessment_status": "AUTOMATED_UNREVIEWED",
                "human_disposition": None,
                "classifier_implementation_authorized": False,
                "scientific_calculation_authorized": False,
            },
        )
    return run


def test__progress__returns_browser_safe_completed_summary(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, assessed=True)
    app = FastAPI()
    app.include_router(
        create_literature_review_router(LiteratureReviewRepository(run))
    )

    response = _request(app, "/literature-review/progress")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "COMPLETE"
    assert payload["original_submission_markdown"] == (
        "# Original framework\n\n$$A = E - TS$$\n"
    )
    assert payload["completion_percent"] == 100.0
    assert payload["status_counts"]["qualified"] == 1
    assert payload["claims"][0]["validation_frame"]["equations"] == [
        {
            "label": "Domain",
            "latex": "0 < x < 1",
            "interpretation": "The endpoints are outside the stated domain.",
        }
    ]
    assert payload["claims"][0]["evidence"] == [
        {
            "label": "E1",
            "citation_key": "source2023",
            "physical_page": 4,
            "quote": "Private retrieved passage.",
        }
    ]
    serialized = response.text
    assert "Private retrieved passage" in serialized
    assert "/private/source.pdf" not in serialized


def test__progress__reports_incremental_retrieval(tmp_path: Path) -> None:
    run = _run(tmp_path, assessed=False)
    app = FastAPI()
    app.include_router(
        create_literature_review_router(LiteratureReviewRepository(run))
    )

    response = _request(app, "/literature-review/progress")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "RETRIEVING"
    assert payload["evidence_ready_count"] == 1
    assert payload["assessment_count"] == 0
    assert payload["claims"][0]["status"] is None


def test__references__stores_content_addressed_private_pdf(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, assessed=True)
    app = FastAPI()
    app.include_router(
        create_literature_review_router(LiteratureReviewRepository(run))
    )
    path = "/literature-review/references"
    data = {
        "claim_id": "C-001",
        "citation_label": "ExampleAuthor2024",
        "doi_or_url": "10.0000/example",
        "note": "Author-supplied copy",
    }
    files = {
        "reference_pdf": (
            "example.pdf",
            b"%PDF-1.7\nprovided source",
            "application/pdf",
        )
    }

    first = _request(app, path, method="POST", data=data, files=files)
    duplicate = _request(app, path, method="POST", data=data, files=files)
    dispositions = run / "provided-references" / "dispositions"
    dispositions.mkdir(mode=0o700)
    _write_json(
        dispositions / "ingested.json",
        {
            "receipt_id": first.json()["receipt_id"],
            "status": "INGESTED_AUTOMATED_UNREVIEWED",
            "latest_generation": "generation-02",
        },
    )
    listed = _request(app, "/literature-review/references")

    assert first.status_code == 201
    assert first.json()["status"] == "RECEIVED_NOT_INGESTED"
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 201
    assert duplicate.json()["duplicate"] is True
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["status"] == (
        "INGESTED_AUTOMATED_UNREVIEWED"
    )
    assert listed.json()["items"][0]["latest_generation"] == "generation-02"
    assert "path" not in first.text
    objects = list((run / "provided-references" / "objects").rglob("*.pdf"))
    records = list((run / "provided-references" / "records").glob("*.json"))
    assert len(objects) == 1
    assert len(records) == 1
    assert stat.S_IMODE(objects[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(records[0].stat().st_mode) == 0o600


def test__references__rejects_non_pdf_body(tmp_path: Path) -> None:
    run = _run(tmp_path, assessed=True)
    app = FastAPI()
    app.include_router(
        create_literature_review_router(LiteratureReviewRepository(run))
    )

    response = _request(
        app,
        "/literature-review/references",
        method="POST",
        data={"claim_id": "C-001", "citation_label": "not-a-pdf"},
        files={
            "reference_pdf": (
                "bad.pdf",
                b"not a PDF",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "provided reference does not have a PDF header"
    )


def test__progress__fails_closed_when_unconfigured() -> None:
    app = FastAPI()
    app.include_router(
        create_literature_review_router(LiteratureReviewRepository(None))
    )

    response = _request(app, "/literature-review/progress")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "literature-review monitoring is not configured"
    )
