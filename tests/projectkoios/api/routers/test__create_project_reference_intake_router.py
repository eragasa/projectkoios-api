from __future__ import annotations

from typing import BinaryIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.project_reference_intake import (
    ProjectMissingPdf,
    ProjectMissingPdfList,
    ProjectPdfBindingDisposition,
    ProjectPdfReceiptDisposition,
    ProjectProvidedPdf,
    ProjectReferenceIntakeConflict,
)
from projectkoios.api.routers.project_reference_intake import (
    create_project_reference_intake_router,
)


class _Provider:
    def __init__(self) -> None:
        self.received: list[tuple[str, bytes, int]] = []
        self.conflict = False

    @property
    def max_pdf_bytes(self) -> int:
        return 64

    def missing_pdfs(self) -> ProjectMissingPdfList:
        return ProjectMissingPdfList(
            collection_id="ksdft2effmass",
            required_count=2,
            bound_count=1,
            not_applicable_count=1,
            missing=(
                ProjectMissingPdf(
                    citekey="missing2026",
                    entry_type="article",
                    title="Sanitized title",
                    authors=("Example, Alice",),
                    year="2026",
                ),
            ),
        )

    def provide_pdf(
        self,
        *,
        citekey: str,
        stream: BinaryIO,
        declared_byte_size: int,
    ) -> ProjectProvidedPdf:
        content = stream.read()
        self.received.append((citekey, content, declared_byte_size))
        if self.conflict:
            raise ProjectReferenceIntakeConflict
        return ProjectProvidedPdf(
            citekey=citekey,
            byte_size=len(content),
            receipt_disposition=ProjectPdfReceiptDisposition.RECEIVED,
            binding_disposition=ProjectPdfBindingDisposition.BOUND,
        )


def _client(provider: _Provider) -> TestClient:
    app = FastAPI()
    app.include_router(create_project_reference_intake_router(provider))
    return TestClient(app)


def test__project_reference_intake__lists_privacy_reduced_missing_pdfs() -> (
    None
):
    provider = _Provider()

    response = _client(provider).get(
        "/project-reference-intake/ksdft2effmass/missing-pdfs"
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": "ksdft2effmass",
        "total_references": 3,
        "required_pdf_count": 2,
        "bound_pdf_count": 1,
        "missing_pdf_count": 1,
        "not_applicable_count": 1,
        "max_pdf_bytes": 64,
        "media_type": "application/pdf",
        "items": [
            {
                "citekey": "missing2026",
                "entry_type": "article",
                "title": "Sanitized title",
                "authors": ["Example, Alice"],
                "year": "2026",
            }
        ],
    }
    serialized = response.text
    assert "sha256" not in serialized.casefold()
    assert "/Users/" not in serialized
    assert "bibtex" not in serialized.casefold()


def test__project_reference_intake__streams_one_pdf_and_binds() -> None:
    provider = _Provider()
    content = b"%PDF-1.7\nsanitized\n%%EOF\n"

    response = _client(provider).post(
        "/project-reference-intake/ksdft2effmass/missing-pdfs/"
        "missing2026/document",
        content=content,
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": "ksdft2effmass",
        "citekey": "missing2026",
        "byte_size": len(content),
        "receipt_disposition": "received",
        "binding_disposition": "bound",
        "document_status": "received-unreviewed",
    }
    assert provider.received == [("missing2026", content, len(content))]
    assert "sha256" not in response.text.casefold()


def test__project_reference_intake__rejects_body_before_owner() -> None:
    provider = _Provider()
    client = _client(provider)
    path = (
        "/project-reference-intake/ksdft2effmass/missing-pdfs/"
        "missing2026/document"
    )

    multipart = client.post(
        path,
        files={"pdf": ("private-name.pdf", b"%PDF-1.7\n", "application/pdf")},
    )
    invalid = client.post(
        path,
        content=b"not a pdf",
        headers={"content-type": "application/pdf"},
    )
    oversized = client.post(
        path,
        content=b"%PDF-" + b"x" * 100,
        headers={"content-type": "application/pdf"},
    )

    assert multipart.status_code == 415
    assert invalid.status_code == 415
    assert oversized.status_code == 413
    assert provider.received == []


def test__project_reference_intake__maps_binding_conflict_without_detail() -> (
    None
):
    provider = _Provider()
    provider.conflict = True

    response = _client(provider).post(
        "/project-reference-intake/ksdft2effmass/missing-pdfs/"
        "missing2026/document",
        content=b"%PDF-1.7\nfixture\n",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "project reference already has a different PDF binding"
    }
