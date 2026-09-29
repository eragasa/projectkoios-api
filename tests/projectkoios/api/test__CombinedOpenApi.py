from __future__ import annotations

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
    OrganizerConfiguration,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.openapi import (
    combined_openapi_bytes,
    combined_openapi_schema,
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_EXPECTED_PATHS = {
    "/",
    "/health",
    "/api/courses",
    "/api/projects",
    "/api/publications",
    "/search",
    "/github/tasks",
    "/citation-reviews",
    "/citation-reviews/sources/{source_name}",
    "/citation-reviews/{claim_id}",
    "/citation-reviews/{claim_id}/decision",
    "/literature-review/progress",
    "/literature-review/references",
    "/equation-reviews",
    "/equation-reviews/{candidate_id}/decision",
    "/equation-reviews/{candidate_id}/region",
    "/organizer/status",
    "/organizer/control",
    "/organizer/events",
    "/organizer/events/stream",
    "/transcript-reviews",
    "/transcript-reviews/{document_id}",
    "/transcript-reviews/{document_id}/source",
    "/transcript-reviews/{document_id}/assets/{asset_id}",
}


def test__combined_openapi__has_exact_integrated_paths_and_methods() -> None:
    schema = combined_openapi_schema()

    assert set(schema["paths"]) == _EXPECTED_PATHS
    expected_methods = {path: {"get"} for path in _EXPECTED_PATHS}
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


def test__combined_openapi__preserves_organizer_event_contracts() -> None:
    schema = combined_openapi_schema()
    schemas = schema["components"]["schemas"]

    event_response = schema["paths"]["/organizer/events"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert event_response == {
        "$ref": "#/components/schemas/OrganizerEventListResponse"
    }
    assert {"OrganizerEventResponse", "OrganizerEventListResponse"} <= set(
        schemas
    )
    assert "OrganizerProposalResponse" not in schemas


def test__combined_openapi__preserves_primary_public_catalog_models() -> None:
    schemas = combined_openapi_schema()["components"]["schemas"]
    code = schemas["PublicCourseRecord"]["properties"]["code"]

    assert code["type"] == "string"
    assert code["pattern"] == "^[A-Z0-9-]{2,32}$"
    assert "CourseCode" not in schemas


def test__combined_openapi__documents_transcript_binary_errors_and_limits() -> (
    None
):
    schema = combined_openapi_schema()
    source = schema["paths"]["/transcript-reviews/{document_id}/source"]["get"]
    preview = schema["paths"][
        "/transcript-reviews/{document_id}/assets/{asset_id}"
    ]["get"]

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
        assert headers["X-Content-Type-Options"]["schema"]["const"] == (
            "nosniff"
        )
        for code in ("404", "500", "502", "503"):
            assert operation["responses"][code]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/ApiErrorResponse"}


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
    assert set(region["responses"]["200"]["content"]) == {"image/png"}
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
    assert "obsidian_markdown" not in request["properties"]
    assert (
        request["properties"]["reviewer_latex"]["anyOf"][0]["maxLength"]
        == 100_000
    )
    assert request["properties"]["display_mode"]["anyOf"][0] == {
        "$ref": "#/components/schemas/EquationDisplayMode"
    }
    assert request["properties"]["render_confirmation"]["anyOf"][0] == {
        "$ref": "#/components/schemas/EquationRenderConfirmation"
    }
    assert request["properties"]["expected_previous_revision"] == {
        "exclusiveMaximum": 9_999.0,
        "minimum": 0,
        "title": "Expected Previous Revision",
        "type": "integer",
    }
    assert {
        "expected_previous_revision",
        "reviewer_latex",
        "display_mode",
        "render_confirmation",
    } <= set(request["required"])

    candidate = schema["components"]["schemas"][
        "EquationReviewCandidateResponse"
    ]
    assert {
        "status",
        "current_revision",
        "expected_previous_revision",
        "display_mode",
    } <= set(candidate["required"])
    response = schema["components"]["schemas"]["EquationReviewDecisionResponse"]
    assert {
        "schema_version",
        "revision_id",
        "recorded_at_utc",
        "reviewer_latex",
        "reviewer_latex_sha256",
        "obsidian_markdown",
        "obsidian_markdown_sha256",
        "render_confirmation",
    } <= set(response["required"])
    proposed = schema["components"]["schemas"][
        "ProposedEquationAssistanceResponse"
    ]
    assert {
        "attempt_id",
        "method",
        "proposal_sha256",
        "proposed_latex",
    } <= set(proposed["required"])
    assert "model_provenance" not in proposed["properties"]
    unassisted = schema["components"]["schemas"][
        "UnassistedEquationProposalResponse"
    ]
    assert unassisted["properties"]["status"]["const"] == "NOT_STARTED"
    failures = schema["components"]["schemas"]["EquationReviewFailureCode"]
    assert {
        "EQUATION_REVIEW_REVIEWER_LATEX_NONCANONICAL",
        "EQUATION_REVIEW_RENDER_STALE",
        "EQUATION_REVIEW_EDIT_AFTER_RENDER",
        "EQUATION_REVIEW_QUEUE_INCOMPLETE",
        "EQUATION_REVIEW_QUEUE_MALFORMED",
    } <= set(failures["enum"])
    queue_response = schema["components"]["schemas"][
        "EquationReviewQueueResponse"
    ]
    assert queue_response["properties"]["items"]["maxItems"] == 256
    assert {
        "contract_id",
        "schema_version",
        "projection_id",
        "package_id",
        "source_sha256",
        "total",
        "decided",
        "pending",
    } <= set(queue_response["required"])
    for code in ("409", "502", "503"):
        assert decision["responses"][code]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/EquationReviewFailureResponse"}


def test__combined_openapi__is_deterministic_and_committed() -> None:
    first = combined_openapi_bytes()
    second = combined_openapi_bytes()
    generated = (
        _REPOSITORY_ROOT / "openapi" / "control.openapi.json"
    ).read_bytes()

    assert first == second
    assert generated == first
    assert json.loads(generated)["openapi"].startswith("3.")


def test__control_app__preserves_organizer_and_defaults_new_ports_unavailable(
    tmp_path: Path,
) -> None:
    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            deployment_profile=DeploymentProfile.CONTROL,
            organizer=OrganizerConfiguration(
                catalog_path=tmp_path / "organizer.sqlite3"
            ),
        )
    )
    client = TestClient(app)

    organizer = client.get("/organizer/status")
    transcripts = client.get("/transcript-reviews")
    equations = client.get(
        "/equation-reviews",
        params={"document_id": "pizzi2020"},
    )

    assert organizer.status_code == 200
    assert organizer.json()["desired_mode"] == "off"
    assert transcripts.status_code == 503
    assert transcripts.json() == {
        "detail": "transcript review provider is unavailable"
    }
    assert equations.status_code == 503
    assert equations.json() == {
        "code": "EQUATION_REVIEW_OWNER_UNAVAILABLE",
        "detail": "equation review owner is unavailable",
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

    assert "projectkoios-agent==0.0.0" in dependencies
    assert not any(
        dependency.startswith("projectkoios-simulations")
        for dependency in dependencies
    )
    assert extra == [
        "projectkoios-applications[pdf-corpus]==0.1.0.dev0",
    ]
    assert "projectkoios-ingestion[pdf]==0.0.0" in development
    assert "projectkoios-simulations" not in sources
    assert sources["projectkoios-applications"] == {
        "path": "../projectkoios-applications",
        "editable": False,
    }
    assert not {"projectkoios-simulations", "physkit"} & locked_names
    assert "Check out published applications owner" in workflow
    assert "b25ba8cc828b2d67bb8b8e20dd6bc5b28515547f" in workflow
    assert "2f32fa9d9b3a5bb452a643dbba34a7dfae461423" in workflow
    assert "e531cff8f65422d9c0cfab5aaa903c1ebdd778c0" in workflow
    assert workflow.index("Check out published applications owner") < (
        workflow.index("Verify locked applications owner")
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
                document_root=root / "document",
            )
        ),
    )
)
assert app.state.deployment_profile == "control"
assert "projectkoios.api.equation_review.owner" in sys.modules
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


def test__equation_and_transcript_boundaries_have_no_owner_imports() -> None:
    source_root = _REPOSITORY_ROOT / "src" / "python" / "projectkoios" / "api"
    boundary_paths = [
        source_root / "boundary_models.py",
        source_root / "equation_review" / "boundary.py",
        source_root / "equation_review" / "models.py",
        source_root / "equation_review" / "repository.py",
        source_root / "equation_review" / "router.py",
        source_root / "transcript_review.py",
        source_root / "transcript_review_models.py",
        source_root / "routers" / "equation_review.py",
        source_root / "routers" / "transcript_review.py",
    ]
    boundary_source = "\n".join(
        path.read_text(encoding="utf-8") for path in boundary_paths
    )

    assert "projectkoios.agent" not in boundary_source
    assert "projectkoios.applications" not in boundary_source
    for forbidden in (
        "from pathlib import",
        "import os",
        "import sqlite3",
        "import subprocess",
        "import threading",
    ):
        assert forbidden not in boundary_source
