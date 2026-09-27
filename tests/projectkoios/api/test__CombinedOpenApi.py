from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.openapi import (
    combined_openapi_bytes,
    combined_openapi_schema,
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_EXISTING_PATHS = {
    "/",
    "/health",
    "/api/publications",
    "/search",
    "/github/tasks",
    "/citation-reviews",
    "/citation-reviews/sources/{source_name}",
    "/citation-reviews/{claim_id}",
    "/citation-reviews/{claim_id}/decision",
    "/literature-review/progress",
    "/literature-review/references",
}
_EXISTING_SCHEMAS = {
    "Body_provide_reference_literature_review_references_post",
    "CitationCandidateResponse",
    "CitationDecisionDisposition",
    "CitationDecisionRequest",
    "CitationDecisionResponse",
    "CitationReviewDetailResponse",
    "CitationReviewQueueResponse",
    "CitationReviewSummaryResponse",
    "GitHubPullRequestSummary",
    "GitHubRepositoryTaskProjection",
    "GitHubTask",
    "GitHubTaskDashboard",
    "GitHubTaskSequence",
    "HTTPValidationError",
    "LiteratureClaimProgressResponse",
    "LiteratureClaimStatus",
    "LiteratureEquationResponse",
    "LiteratureEvidenceReferenceResponse",
    "LiteratureReviewPhase",
    "LiteratureReviewProgressResponse",
    "LiteratureStatusCountResponse",
    "LiteratureValidationFrameResponse",
    "ManuscriptEquationResponse",
    "ProvidedReferenceListResponse",
    "ProvidedReferenceResponse",
    "ProvidedReferenceStatus",
    "PublicationCatalog",
    "PublicationKind",
    "PublicationLink",
    "PublicationRecord",
    "SearchRequest",
    "SearchResult",
    "ValidationError",
}
_RECONCILED_SCHEMAS = {
    "CourseMaterialsStatus",
    "LifeDomain",
    "OrganizerControlRequest",
    "OrganizerProposalListResponse",
    "OrganizerProposalResponse",
    "OrganizerStatusResponse",
    "PublicCapabilityStatus",
    "PublicCourseCatalog",
    "PublicCourseInstitution",
    "PublicCourseRecord",
    "PublicCourseSource",
    "PublicProjectCapability",
    "PublicProjectCatalog",
    "PublicProjectLink",
    "PublicProjectRecord",
    "PublicProjectReview",
    "PublicProjectSourceRevision",
    "PublicProjectStatus",
    "TranscriptReviewCategory",
    "TranscriptReviewDocumentResponse",
    "TranscriptReviewDocumentSummaryResponse",
    "TranscriptReviewItemResponse",
    "TranscriptReviewLinkRelation",
    "TranscriptReviewLinkResolution",
    "TranscriptReviewLinkResponse",
    "TranscriptReviewQueueResponse",
    "TranscriptReviewRegionResponse",
    "TranscriptReviewRisk",
    "TranscriptReviewStatus",
}
_NEW_PATHS = {
    "/api/courses",
    "/api/projects",
    "/organizer/status",
    "/organizer/control",
    "/organizer/proposals",
    "/transcript-reviews",
    "/transcript-reviews/{document_id}",
    "/transcript-reviews/{document_id}/source",
    "/transcript-reviews/{document_id}/assets/{asset_id}",
}


def test__combined_openapi__preserves_existing_paths_and_schemas() -> None:
    schema = combined_openapi_schema()

    assert _EXISTING_PATHS <= set(schema["paths"])
    assert _EXISTING_SCHEMAS <= set(schema["components"]["schemas"])
    assert _RECONCILED_SCHEMAS <= set(schema["components"]["schemas"])
    assert _NEW_PATHS <= set(schema["paths"])


def test__combined_openapi__excludes_underspecified_event_contracts() -> None:
    schema = combined_openapi_schema()

    assert "/organizer/events" not in schema["paths"]
    assert "/organizer/events/stream" not in schema["paths"]


def test__combined_openapi__uses_nominal_owner_projected_course_code() -> None:
    schemas = combined_openapi_schema()["components"]["schemas"]

    assert schemas["CourseCode"]["type"] == "string"
    assert schemas["PublicCourseRecord"]["properties"]["code"] == {
        "$ref": "#/components/schemas/CourseCode"
    }
    assert schemas["OrganizerProposalResponse"]["properties"]["course_code"][
        "anyOf"
    ][0] == {"$ref": "#/components/schemas/CourseCode"}
    assert "course_code" in schemas["OrganizerProposalResponse"]["required"]


def test__combined_openapi__documents_binary_errors_and_limits() -> None:
    schema = combined_openapi_schema()
    source = schema["paths"]["/transcript-reviews/{document_id}/source"]["get"]
    proposals = schema["paths"]["/organizer/proposals"]["get"]
    limit = next(
        parameter
        for parameter in proposals["parameters"]
        if parameter["name"] == "limit"
    )

    assert source["responses"]["200"]["content"]["application/pdf"][
        "schema"
    ] == {"format": "binary", "type": "string"}
    assert source["responses"]["404"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ApiErrorResponse"}
    assert source["responses"]["503"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ApiErrorResponse"}
    assert limit["schema"]["minimum"] == 1
    assert limit["schema"]["maximum"] == 500


def test__combined_openapi__is_deterministic_and_committed() -> None:
    first = combined_openapi_bytes()
    second = combined_openapi_bytes()
    generated = (
        _REPOSITORY_ROOT / "openapi" / "control.openapi.json"
    ).read_bytes()

    assert first == second
    assert generated == first
    assert json.loads(generated)["openapi"].startswith("3.")


def test__control_app__defaults_new_owner_contracts_to_unavailable() -> None:
    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            deployment_profile=DeploymentProfile.CONTROL
        )
    )
    client = TestClient(app)

    organizer = client.get("/organizer/status")
    transcripts = client.get("/transcript-reviews")

    assert organizer.status_code == 503
    assert organizer.json() == {"detail": "organizer provider is unavailable"}
    assert transcripts.status_code == 503
    assert transcripts.json() == {
        "detail": "transcript review provider is unavailable"
    }


def test__public_openapi__keeps_control_contracts_absent() -> None:
    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            deployment_profile=DeploymentProfile.PUBLIC
        )
    )
    paths = set(app.openapi()["paths"])

    assert {"/api/courses", "/api/projects", "/api/publications"} <= paths
    assert (
        not {
            "/github/tasks",
            "/organizer/status",
            "/transcript-reviews",
        }
        & paths
    )


def test__review_contracts__have_no_agent_or_owner_runtime_imports() -> None:
    source_root = _REPOSITORY_ROOT / "src" / "python" / "projectkoios" / "api"
    all_api_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    )
    boundary_paths = [
        source_root / "course_models.py",
        source_root / "organizer_models.py",
        source_root / "project_models.py",
        source_root / "public_catalogs.py",
        source_root / "transcript_review.py",
        source_root / "transcript_review_models.py",
        source_root / "routers" / "courses.py",
        source_root / "routers" / "organizer.py",
        source_root / "routers" / "projects.py",
        source_root / "routers" / "transcript_review.py",
    ]
    boundary_source = "\n".join(
        path.read_text(encoding="utf-8") for path in boundary_paths
    )

    assert "projectkoios.agent" not in all_api_source
    for forbidden in (
        "from pathlib import",
        "import os",
        "import sqlite3",
        "import subprocess",
        "import threading",
    ):
        assert forbidden not in boundary_source
