from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
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
    "ApiErrorResponse",
    "CourseCode",
    "CourseMaterialsStatus",
    "DeterministicEquationEvidenceResponse",
    "EquationRegionEvidenceResponse",
    "EquationReviewCandidateResponse",
    "EquationReviewDecision",
    "EquationReviewDecisionRequest",
    "EquationReviewDecisionResponse",
    "EquationReviewDisposition",
    "EquationReviewFailureCode",
    "EquationReviewFailureResponse",
    "EquationReviewQueueResponse",
    "EquationSourceIdentityResponse",
    "LifeDomain",
    "OrganizerActivity",
    "OrganizerControlMode",
    "OrganizerControlRequest",
    "OrganizerFileAvailability",
    "OrganizerParaCategory",
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
    "PendingEquationAssistanceResponse",
    "ProposedEquationAssistanceResponse",
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
_MASTER_PATHS_SHA256 = (
    "5365d4194d9bb3eb177707cc095a58fa0e7bf5c759756766042298e44ee1edc5"
)
_MASTER_SCHEMAS_SHA256 = (
    "ff502fac5c5032934143a08a68e0ceb5e10e060c5a2ff94225c928c42bb47633"
)
_NEW_PATHS = {
    "/api/courses",
    "/api/projects",
    "/equation-reviews",
    "/equation-reviews/{candidate_id}/decision",
    "/equation-reviews/{candidate_id}/region",
    "/organizer/status",
    "/organizer/control",
    "/organizer/proposals",
    "/transcript-reviews",
    "/transcript-reviews/{document_id}",
    "/transcript-reviews/{document_id}/source",
    "/transcript-reviews/{document_id}/assets/{asset_id}",
}


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test__combined_openapi__is_exact_selected_master_superset() -> None:
    schema = combined_openapi_schema()

    assert set(schema["paths"]) == _EXISTING_PATHS | _NEW_PATHS
    assert set(schema["components"]["schemas"]) == (
        _EXISTING_SCHEMAS | _RECONCILED_SCHEMAS
    )
    master_paths = {
        name: schema["paths"][name] for name in sorted(_EXISTING_PATHS)
    }
    master_schemas = {
        name: schema["components"]["schemas"][name]
        for name in sorted(_EXISTING_SCHEMAS)
    }
    assert _canonical_sha256(master_paths) == _MASTER_PATHS_SHA256
    assert _canonical_sha256(master_schemas) == _MASTER_SCHEMAS_SHA256
    expected_methods = {path: {"get"} for path in _EXISTING_PATHS | _NEW_PATHS}
    expected_methods.update(
        {
            "/citation-reviews/{claim_id}/decision": {"put"},
            "/equation-reviews/{candidate_id}/decision": {"put"},
            "/literature-review/references": {"get", "post"},
            "/organizer/control": {"put"},
            "/search": {"post"},
        }
    )
    observed_methods = {
        path: set(item) - {"parameters"}
        for path, item in schema["paths"].items()
    }
    assert observed_methods == expected_methods


def test__combined_openapi__excludes_underspecified_event_contracts() -> None:
    schema = combined_openapi_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert "/organizer/events" not in schema["paths"]
    assert "/organizer/events/stream" not in schema["paths"]
    assert "OrganizerEvent" not in serialized
    assert "#/components/schemas/OrganizerEvent" not in serialized


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
    preview = schema["paths"][
        "/transcript-reviews/{document_id}/assets/{asset_id}"
    ]["get"]
    proposals = schema["paths"]["/organizer/proposals"]["get"]
    limit = next(
        parameter
        for parameter in proposals["parameters"]
        if parameter["name"] == "limit"
    )

    source_schema = source["responses"]["200"]["content"]["application/pdf"][
        "schema"
    ]
    assert source_schema == {
        "format": "binary",
        "minLength": 1,
        "type": "string",
        "x-maximum-bytes": 100_000_000,
    }
    for media_type in ("image/jpeg", "image/png", "image/webp"):
        assert (
            preview["responses"]["200"]["content"][media_type]["schema"][
                "x-maximum-bytes"
            ]
            == 20_000_000
        )
    for operation in (source, preview):
        assert (
            "fully buffered in memory"
            in operation["responses"]["200"]["description"]
        )
        headers = operation["responses"]["200"]["headers"]
        assert headers["Content-Disposition"]["schema"]["const"] == "inline"
        assert headers["X-Content-Type-Options"]["schema"]["const"] == "nosniff"
        for code in ("404", "500", "502", "503"):
            assert operation["responses"][code]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/ApiErrorResponse"}
    assert limit["schema"]["minimum"] == 1
    assert limit["schema"]["maximum"] == 500


def test__combined_openapi__publishes_safe_equation_review_boundary() -> None:
    schema = combined_openapi_schema()
    queue = schema["paths"]["/equation-reviews"]["get"]
    region = schema["paths"]["/equation-reviews/{candidate_id}/region"]["get"]
    decision = schema["paths"]["/equation-reviews/{candidate_id}/decision"][
        "put"
    ]

    document_id = next(
        parameter
        for parameter in queue["parameters"]
        if parameter["name"] == "document_id"
    )
    assert document_id["required"] is True
    assert queue["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EquationReviewQueueResponse"}
    assert set(region["responses"]["200"]["content"]) == {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    for media in region["responses"]["200"]["content"].values():
        assert media["schema"]["x-maximum-bytes"] == 20_000_000
    assert decision["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EquationReviewDecisionRequest"
    }
    assert decision["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/EquationReviewDecisionResponse"}
    request = schema["components"]["schemas"]["EquationReviewDecisionRequest"]
    assert "recorded_at_utc" not in request["properties"]
    assert request["properties"]["expected_previous_revision"] == {
        "exclusiveMaximum": 9_999.0,
        "minimum": 0,
        "title": "Expected Previous Revision",
        "type": "integer",
    }
    assert "expected_previous_revision" in request["required"]
    assert (
        schema["components"]["schemas"]["EquationReviewQueueResponse"][
            "properties"
        ]["items"]["maxItems"]
        == 256
    )
    for code in ("409", "503"):
        assert decision["responses"][code]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/EquationReviewFailureResponse"}


def test__combined_openapi__declares_fixed_provider_error_envelopes() -> None:
    schema = combined_openapi_schema()
    operations = [
        ("/api/courses", "get"),
        ("/api/projects", "get"),
        ("/organizer/status", "get"),
        ("/organizer/control", "put"),
        ("/organizer/proposals", "get"),
        ("/transcript-reviews", "get"),
        ("/transcript-reviews/{document_id}", "get"),
        ("/transcript-reviews/{document_id}/source", "get"),
        (
            "/transcript-reviews/{document_id}/assets/{asset_id}",
            "get",
        ),
    ]

    for path, method in operations:
        responses = schema["paths"][path][method]["responses"]
        for code in ("500", "502", "503"):
            assert responses[code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ApiErrorResponse"
            }


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
    equations = client.get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert organizer.status_code == 503
    assert organizer.json() == {"detail": "organizer provider is unavailable"}
    assert transcripts.status_code == 503
    assert transcripts.json() == {
        "detail": "transcript review provider is unavailable"
    }
    assert equations.status_code == 503
    assert equations.json() == {
        "code": "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        "detail": "equation review evidence is unavailable",
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
            "/equation-reviews",
            "/github/tasks",
            "/organizer/status",
            "/transcript-reviews",
        }
        & paths
    )


def test__equation_owner__has_narrow_locked_dependency_seam() -> None:
    project = tomllib.loads(
        (_REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    lock = tomllib.loads(
        (_REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8")
    )
    dependencies = project["project"]["dependencies"]
    extra = project["project"]["optional-dependencies"][
        "equation-review-control"
    ]
    development = project["project"]["optional-dependencies"]["dev"]
    sources = project["tool"]["uv"]["sources"]
    locked_names = {package["name"] for package in lock["package"]}
    workflow = (_REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )

    assert not any(
        dependency.startswith("projectkoios-simulations")
        for dependency in dependencies
    )
    assert extra == [
        "projectkoios-applications[pdf-corpus]==0.1.0.dev0",
    ]
    assert "projectkoios-ingestion[pdf]==0.0.0" in development
    assert "projectkoios-simulations" not in sources
    assert not {"projectkoios-simulations", "physkit"} & locked_names
    assert "projectkoios-applications 1e331a9 is unpushed" in workflow
    assert "1e331a9527434938d0aa8ae7bfc4a99bddc87d9d" in workflow
    assert "Check out locked applications owner" in workflow
    assert workflow.index("Report unavailable applications owner source") < (
        workflow.index("Check out locked applications owner")
    )
    assert "projectkoios-simulations" not in workflow


def test__configured_control__imports_pdf_corpus_without_simulations() -> None:
    environment = dict(os.environ)
    script = """
import sys
from importlib.abc import MetaPathFinder
from pathlib import Path

class RejectSimulationImports(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "physkit" or fullname.startswith(
            "projectkoios.simulations"
        ):
            raise RuntimeError(f"forbidden capability import: {fullname}")
        return None

sys.meta_path.insert(0, RejectSimulationImports())
from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    EquationReviewConfiguration,
    EquationReviewDocumentConfiguration,
    ProjectKoiosAppConfiguration,
)
root = Path.cwd() / "deliberately-unavailable-test-root"
app = ProjectKoiosApp.create_app(
    configuration=ProjectKoiosAppConfiguration(
        deployment_profile=DeploymentProfile.CONTROL,
        equation_review=EquationReviewConfiguration(
            pizzi2020=EquationReviewDocumentConfiguration(
                bundle_path=root / "bundle.json",
                regions_root=root / "regions",
                document_root=root / "document",
            )
        ),
    )
)
assert app.state.deployment_profile == "control"
assert "projectkoios.api.equation_review_owner" in sys.modules
assert "projectkoios.applications.pdf_corpus_ingestion" in sys.modules
assert "physkit" not in sys.modules
assert not any(
    name == "projectkoios.simulations"
    or name.startswith("projectkoios.simulations.")
    for name in sys.modules
)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


def test__public_startup__does_not_import_applications_owner_chain() -> None:
    source_root = _REPOSITORY_ROOT / "src" / "python"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source_root)
    script = """
import sys
from importlib.abc import MetaPathFinder

class RejectApplicationsImports(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "projectkoios.applications" or fullname.startswith(
            "projectkoios.applications."
        ):
            raise RuntimeError(f"private extra import attempted: {fullname}")
        return None

sys.meta_path.insert(0, RejectApplicationsImports())
from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)
app = ProjectKoiosApp.create_app(
    configuration=ProjectKoiosAppConfiguration(
        deployment_profile=DeploymentProfile.PUBLIC,
    )
)
assert app.state.deployment_profile == "public"
assert not any(
    name == "projectkoios.applications"
    or name.startswith("projectkoios.applications.")
    for name in sys.modules
)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


def test__review_contracts__have_no_agent_or_owner_runtime_imports() -> None:
    source_root = _REPOSITORY_ROOT / "src" / "python" / "projectkoios" / "api"
    all_api_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    )
    boundary_paths = [
        source_root / "course_models.py",
        source_root / "equation_review_boundary.py",
        source_root / "equation_review_models.py",
        source_root / "organizer_models.py",
        source_root / "project_models.py",
        source_root / "public_catalogs.py",
        source_root / "transcript_review.py",
        source_root / "transcript_review_models.py",
        source_root / "routers" / "courses.py",
        source_root / "routers" / "equation_review.py",
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
