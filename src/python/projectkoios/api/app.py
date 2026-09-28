from __future__ import annotations

from fastapi import FastAPI
from projectkoios.api.citation_review import CitationReviewRepository
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.equation_review import EquationReviewRepository
from projectkoios.api.github_tasks import GitHubTaskReader
from projectkoios.api.literature_review import LiteratureReviewRepository
from projectkoios.api.public_catalogs import (
    EmptyPublicCourseProvider,
    EmptyPublicProjectProvider,
)
from projectkoios.api.publications import PublicationRepository
from projectkoios.api.routers.citation_review import (
    create_citation_review_router,
)
from projectkoios.api.routers.core import create_core_router
from projectkoios.api.routers.courses import (
    PublicCourseProvider,
    create_courses_router,
)
from projectkoios.api.routers.equation_review import (
    create_equation_review_router,
)
from projectkoios.api.routers.github_tasks import (
    GitHubTaskProvider,
    create_github_tasks_router,
)
from projectkoios.api.routers.literature_review import (
    create_literature_review_router,
)
from projectkoios.api.routers.organizer import (
    OrganizerProvider,
    create_organizer_router,
)
from projectkoios.api.routers.projects import (
    PublicProjectProvider,
    create_projects_router,
)
from projectkoios.api.routers.publications import create_publications_router
from projectkoios.api.routers.search import create_search_router
from projectkoios.api.routers.transcript_review import (
    create_transcript_review_router,
)
from projectkoios.api.transcript_review import TranscriptReviewProvider
from projectkoios.runtime import ProjectKoiosServices, create_services


class ProjectKoiosApp:
    def __init__(
        self,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
        courses: PublicCourseProvider | None = None,
        projects: PublicProjectProvider | None = None,
        organizer: OrganizerProvider | None = None,
        transcript_reviews: TranscriptReviewProvider | None = None,
    ) -> None:
        self.configuration = configuration or ProjectKoiosAppConfiguration()
        self.courses = (
            courses if courses is not None else EmptyPublicCourseProvider()
        )
        self.projects = (
            projects if projects is not None else EmptyPublicProjectProvider()
        )
        self.publications = PublicationRepository(
            self.configuration.publications.catalog_path
        )

        self.app = FastAPI(
            title=self.configuration.title,
            version=self.configuration.version,
            debug=self.configuration.debug,
        )
        self.app.state.deployment_profile = (
            self.configuration.deployment_profile.value
        )

        self.app.include_router(create_core_router())
        self.app.include_router(create_courses_router(self.courses))
        self.app.include_router(create_projects_router(self.projects))
        self.app.include_router(create_publications_router(self.publications))

        if self.configuration.deployment_profile is DeploymentProfile.CONTROL:
            self._register_control_routes(
                services,
                github_tasks,
                organizer,
                transcript_reviews,
            )

    def _register_control_routes(
        self,
        services: ProjectKoiosServices | None,
        github_tasks: GitHubTaskProvider | None,
        organizer: OrganizerProvider | None,
        transcript_reviews: TranscriptReviewProvider | None,
    ) -> None:
        control_services = services or create_services(self.configuration)
        citation_review = self.configuration.citation_review
        citation_reviews = CitationReviewRepository(
            citation_review.bundle_path,
            citation_review.decisions_path,
            citation_review.sources_root,
        )
        literature_reviews = LiteratureReviewRepository(
            self.configuration.literature_review.run_path
        )
        equation_reviews = EquationReviewRepository(
            self.configuration.equation_review
        )

        github_task_provider = github_tasks or GitHubTaskReader(
            self.configuration.github.repositories,
            executable=self.configuration.github.executable,
        )

        self.app.include_router(create_search_router(control_services.search))
        self.app.include_router(
            create_github_tasks_router(github_task_provider)
        )
        self.app.include_router(create_citation_review_router(citation_reviews))
        self.app.include_router(
            create_literature_review_router(literature_reviews)
        )
        self.app.include_router(create_equation_review_router(equation_reviews))
        self.app.include_router(create_organizer_router(organizer))
        self.app.include_router(
            create_transcript_review_router(transcript_reviews)
        )

    @classmethod
    def create_app(
        cls,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
        courses: PublicCourseProvider | None = None,
        projects: PublicProjectProvider | None = None,
        organizer: OrganizerProvider | None = None,
        transcript_reviews: TranscriptReviewProvider | None = None,
    ) -> FastAPI:
        projectkoios_app = cls(
            configuration=configuration,
            services=services,
            github_tasks=github_tasks,
            courses=courses,
            projects=projects,
            organizer=organizer,
            transcript_reviews=transcript_reviews,
        )
        return projectkoios_app.app
