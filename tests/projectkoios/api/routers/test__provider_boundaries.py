from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from projectkoios.api.course_models import (
    CourseCode,
    CourseMaterialsStatus,
    PublicCourseCatalog,
    PublicCourseInstitution,
    PublicCourseRecord,
    PublicCourseSource,
)
from projectkoios.api.organizer_models import (
    LifeDomain,
    OrganizerActivity,
    OrganizerControlMode,
    OrganizerProposalListResponse,
    OrganizerProposalResponse,
    OrganizerStatusResponse,
)
from projectkoios.api.project_models import (
    PublicCapabilityStatus,
    PublicProjectCapability,
    PublicProjectCatalog,
    PublicProjectLink,
    PublicProjectRecord,
    PublicProjectReview,
    PublicProjectSourceRevision,
    PublicProjectStatus,
)
from projectkoios.api.provider_boundary import invoke_provider
from projectkoios.api.routers.courses import create_courses_router
from projectkoios.api.routers.organizer import create_organizer_router
from projectkoios.api.routers.projects import create_projects_router
from projectkoios.api.routers.transcript_review import (
    create_transcript_review_router,
)
from projectkoios.api.transcript_review import TranscriptReviewResource
from projectkoios.api.transcript_review_models import (
    TranscriptReviewDocumentResponse,
    TranscriptReviewDocumentSummaryResponse,
    TranscriptReviewItemResponse,
    TranscriptReviewQueueResponse,
    TranscriptReviewRegionResponse,
)
from pydantic import HttpUrl

_SECRET = "provider-secret-must-not-escape"


def _client(*routers: object) -> TestClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router)  # type: ignore[arg-type]
    return TestClient(app)


class _RuntimeCourse:
    def list_courses(self) -> PublicCourseCatalog:
        raise RuntimeError(_SECRET)


class _RuntimeProject:
    def list_projects(self) -> PublicProjectCatalog:
        raise RuntimeError(_SECRET)


class _RuntimeOrganizer:
    def read_status(self) -> OrganizerStatusResponse:
        raise RuntimeError(_SECRET)

    def set_control(
        self,
        mode: OrganizerControlMode,
    ) -> OrganizerStatusResponse:
        raise RuntimeError(f"{_SECRET}:{mode}")

    def list_proposals(
        self,
        *,
        life_domain: LifeDomain,
        limit: int,
    ) -> OrganizerProposalListResponse:
        raise RuntimeError(f"{_SECRET}:{life_domain}:{limit}")


class _RuntimeTranscript:
    def read_queue(self) -> TranscriptReviewQueueResponse:
        raise RuntimeError(_SECRET)

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse:
        raise RuntimeError(f"{_SECRET}:{document_id}")

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        raise RuntimeError(f"{_SECRET}:{document_id}")

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        raise RuntimeError(f"{_SECRET}:{document_id}:{asset_id}")


def test__provider_boundary__does_not_catch_cancellation_or_system_exit() -> (
    None
):
    for exit_error in (asyncio.CancelledError(), SystemExit(2)):
        with pytest.raises(type(exit_error)):
            invoke_provider(lambda error=exit_error: _raise_base(error))


def _raise_base(error: BaseException) -> None:
    raise error


def test__provider_boundaries__map_runtime_error_on_every_new_route() -> None:
    course_client = _client(create_courses_router(_RuntimeCourse()))
    project_client = _client(create_projects_router(_RuntimeProject()))
    organizer_client = _client(create_organizer_router(_RuntimeOrganizer()))
    transcript_client = _client(
        create_transcript_review_router(_RuntimeTranscript())
    )

    responses = [
        course_client.get("/api/courses"),
        project_client.get("/api/projects"),
        organizer_client.get("/organizer/status"),
        organizer_client.put("/organizer/control", json={"mode": "off"}),
        organizer_client.get("/organizer/proposals"),
        transcript_client.get("/transcript-reviews"),
        transcript_client.get("/transcript-reviews/document-001"),
        transcript_client.get("/transcript-reviews/document-001/source"),
        transcript_client.get(
            "/transcript-reviews/document-001/assets/preview-001"
        ),
    ]

    assert all(response.status_code == 500 for response in responses)
    assert all(
        response.json()["detail"].endswith("failed unexpectedly")
        for response in responses
    )
    assert all(_SECRET not in response.text for response in responses)


def _malformed_course_catalog() -> PublicCourseCatalog:
    course = PublicCourseRecord.model_construct(
        id="institution.course",
        code=CourseCode("COURSE-1"),
        title="x" * 241,
        materials_status=CourseMaterialsStatus.PUBLISHED,
    )
    institution = PublicCourseInstitution.model_construct(
        id="institution",
        name="Institution",
        courses=(course,),
    )
    return PublicCourseCatalog.model_construct(
        schema_version="1",
        reviewed_on=date(2026, 9, 27),
        source=PublicCourseSource(
            repository="owner/repository",
            revision="a" * 40,
            url="https://example.test/source",
        ),
        publication_boundary=("Reviewed",),
        institutions=(institution,),
        unresolved_collections=(),
    )


class _MalformedCourse:
    def list_courses(self) -> PublicCourseCatalog:
        return _malformed_course_catalog()


def _malformed_project_catalog() -> PublicProjectCatalog:
    invalid_link = PublicProjectLink.model_construct(
        label="x" * 81,
        url=HttpUrl("https://example.test/evidence"),
    )
    project = PublicProjectRecord.model_construct(
        id="project-1",
        slug="project-1",
        name="Project",
        tagline="Tagline",
        summary="Summary",
        status=PublicProjectStatus.MAINTAINED,
        review=PublicProjectReview(
            record_version="1.0.0",
            reviewed_on=date(2026, 9, 27),
            review_url="https://example.test/review",
        ),
        source_revisions=(
            PublicProjectSourceRevision(
                repository="owner/repository",
                revision="a" * 40,
                url="https://example.test/source",
            ),
        ),
        evidence=(invalid_link,),
        topics=(),
        purposes=("Purpose",),
        principles=(),
        capabilities=(
            PublicProjectCapability(
                name="Capability",
                status=PublicCapabilityStatus.AVAILABLE,
                summary="Summary",
            ),
        ),
        limitations=(),
        links=(),
    )
    return PublicProjectCatalog.model_construct(
        schema_version="1",
        projects=(project,),
    )


class _MalformedProject:
    def list_projects(self) -> PublicProjectCatalog:
        return _malformed_project_catalog()


def _malformed_status() -> OrganizerStatusResponse:
    return OrganizerStatusResponse.model_construct(
        desired_mode=OrganizerControlMode.OFF,
        activity=OrganizerActivity.OFF,
        discovered_roots=0,
        observed_files=0,
        local_files=0,
        placeholder_files=0,
        proposed_files=0,
        last_event_sequence=0,
        current_root_id="1" * 64,
        current_relative_path="../private",
        last_error=None,
    )


def _malformed_proposals() -> OrganizerProposalListResponse:
    proposal = OrganizerProposalResponse.model_construct(
        file_id="1" * 64,
        root_id="2" * 64,
        relative_path="Courses//private.txt",
        name="private.txt",
        extension=".txt",
        byte_size=1,
        availability="local",
        para_category="resource",
        life_domain="teaching",
        course_code=None,
        confidence=0.5,
        suggested_group="Group",
        rationale="Rationale",
        model="model",
        model_digest="3" * 64,
        proposed_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    return OrganizerProposalListResponse.model_construct(
        proposals=(proposal,),
        total=1,
        complete=True,
    )


class _MalformedOrganizer:
    def read_status(self) -> OrganizerStatusResponse:
        return _malformed_status()

    def set_control(
        self,
        mode: OrganizerControlMode,
    ) -> OrganizerStatusResponse:
        return _malformed_status()

    def list_proposals(
        self,
        *,
        life_domain: LifeDomain,
        limit: int,
    ) -> OrganizerProposalListResponse:
        return _malformed_proposals()


def _summary() -> TranscriptReviewDocumentSummaryResponse:
    return TranscriptReviewDocumentSummaryResponse(
        document_id="document-001",
        display_name="Document",
        source_id="source:001",
        status="AUTOMATED_UNREVIEWED",
        artifact_generation=1,
        physical_page_count=1,
        total_items=0,
        pending_items=0,
        categories=(),
    )


def _malformed_queue() -> TranscriptReviewQueueResponse:
    summary = _summary().model_copy(update={"source_id": "../private.pdf"})
    return TranscriptReviewQueueResponse.model_construct(
        review_id="review-001",
        title="Review",
        status="AUTOMATED_UNREVIEWED",
        total_documents=1,
        total_items=0,
        pending_items=0,
        documents=(summary,),
    )


def _malformed_document() -> TranscriptReviewDocumentResponse:
    region = TranscriptReviewRegionResponse.model_construct(
        x0=0.0,
        y0=0.0,
        x1=float("nan"),
        y1=1.0,
    )
    item = TranscriptReviewItemResponse.model_construct(
        item_id="item-001",
        category="FIGURE",
        risk="REVIEW_REQUIRED",
        physical_page=1,
        printed_page=None,
        region=region,
        source_text="source",
        predecessor_text=None,
        projected_text=None,
        explanation="explanation",
        flags=(),
        preview_asset_id="preview-001",
        links=(),
    )
    return TranscriptReviewDocumentResponse.model_construct(
        **_summary().model_dump(
            exclude={"total_items", "pending_items", "categories"}
        ),
        total_items=1,
        pending_items=1,
        categories=("FIGURE",),
        manifest_id="manifest:001",
        clean_artifact_id="clean:001",
        source_sha256="a" * 64,
        limitations=(),
        items=(item,),
    )


class _MalformedTranscript:
    def read_queue(self) -> TranscriptReviewQueueResponse:
        return _malformed_queue()

    def read_document(
        self,
        document_id: str,
    ) -> TranscriptReviewDocumentResponse:
        return _malformed_document()

    def read_source(self, document_id: str) -> TranscriptReviewResource:
        return TranscriptReviewResource(
            body=b"\x89PNG\r\n\x1a\n",
            media_type="application/pdf",
        )

    def read_preview(
        self,
        document_id: str,
        asset_id: str,
    ) -> TranscriptReviewResource:
        return TranscriptReviewResource(
            body=b"RIFF0000NOPE",
            media_type="image/webp",
        )


def test__provider_boundaries__rejects_all_malformed_output() -> None:
    course_client = _client(create_courses_router(_MalformedCourse()))
    project_client = _client(create_projects_router(_MalformedProject()))
    organizer_client = _client(create_organizer_router(_MalformedOrganizer()))
    transcript_client = _client(
        create_transcript_review_router(_MalformedTranscript())
    )

    responses = [
        course_client.get("/api/courses"),
        project_client.get("/api/projects"),
        organizer_client.get("/organizer/status"),
        organizer_client.put("/organizer/control", json={"mode": "off"}),
        organizer_client.get("/organizer/proposals"),
        transcript_client.get("/transcript-reviews"),
        transcript_client.get("/transcript-reviews/document-001"),
        transcript_client.get("/transcript-reviews/document-001/source"),
        transcript_client.get(
            "/transcript-reviews/document-001/assets/preview-001"
        ),
    ]

    assert all(response.status_code == 502 for response in responses)
    assert all(
        response.json()["detail"].endswith("invalid projection")
        for response in responses
    )
    assert all("private" not in response.text for response in responses)
