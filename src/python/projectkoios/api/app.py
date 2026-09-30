from __future__ import annotations

from fastapi import FastAPI
from projectkoios.agent.organizer import OrganizerCatalog
from projectkoios.api.citation_review import CitationReviewRepository
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.courses import PublicCourseRepository
from projectkoios.api.equation_review import (
    EquationReviewOwner,
    EquationReviewRepository,
)
from projectkoios.api.github_tasks import GitHubTaskReader
from projectkoios.api.literature_review import LiteratureReviewRepository
from projectkoios.api.projects import PublicProjectRepository
from projectkoios.api.publications import PublicationRepository
from projectkoios.api.routers.citation_review import (
    create_citation_review_router,
)
from projectkoios.api.routers.core import create_core_router
from projectkoios.api.routers.courses import create_courses_router
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
from projectkoios.api.routers.projects import create_projects_router
from projectkoios.api.routers.publications import create_publications_router
from projectkoios.api.routers.search import create_search_router
from projectkoios.api.routers.transcript_review import (
    create_transcript_review_router,
)
from projectkoios.api.routers.transcripts import create_transcripts_router
from projectkoios.api.transcript_review import TranscriptReviewProvider
from projectkoios.api.transcripts import (
    TranscriptOwner,
    TranscriptProvider,
    TranscriptRepository,
)
from projectkoios.runtime import ProjectKoiosServices, create_services


class ProjectKoiosApp:
    def __init__(
        self,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
        organizer: OrganizerProvider | None = None,
        transcript_reviews: TranscriptReviewProvider | None = None,
        transcripts: TranscriptProvider | None = None,
    ) -> None:
        self.configuration = configuration or ProjectKoiosAppConfiguration()
        self.courses = PublicCourseRepository(
            self.configuration.courses.catalog_path
        )
        self.publications = PublicationRepository(
            self.configuration.publications.catalog_path
        )
        self.projects = PublicProjectRepository(
            self.configuration.projects.catalog_path
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
                transcripts,
            )

    def _register_control_routes(
        self,
        services: ProjectKoiosServices | None,
        github_tasks: GitHubTaskProvider | None,
        organizer: OrganizerProvider | None,
        transcript_reviews: TranscriptReviewProvider | None,
        transcripts: TranscriptProvider | None,
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
        equation_review = self.configuration.equation_review
        equation_owner: EquationReviewOwner | None = None
        if equation_review.pizzi2020 is not None:
            from projectkoios.api.equation_review.owner import (
                ApplicationsEquationReviewOwner,
            )

            equation_owner = ApplicationsEquationReviewOwner(
                equation_review.pizzi2020.document_root
            )
        equation_reviews = EquationReviewRepository(
            equation_review,
            owner=equation_owner,
        )

        github_task_provider = github_tasks or GitHubTaskReader(
            self.configuration.github.repositories,
            executable=self.configuration.github.executable,
        )
        organizer_provider = organizer or OrganizerCatalog(
            self.configuration.organizer.catalog_path
        )
        transcript_provider = transcripts
        if transcript_provider is None:
            transcript_owner: TranscriptOwner | None = None
            transcript_root = self.configuration.transcripts.document_root
            if transcript_root is not None:
                from projectkoios.api.transcript_owner import (
                    ApplicationsTranscriptOwner,
                )

                transcript_owner = ApplicationsTranscriptOwner(transcript_root)
            transcript_provider = TranscriptRepository(
                self.configuration.transcripts,
                owner=transcript_owner,
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
        self.app.include_router(create_organizer_router(organizer_provider))
        self.app.include_router(create_transcripts_router(transcript_provider))
        self.app.include_router(
            create_transcript_review_router(transcript_reviews)
        )

    @classmethod
    def create_app(
        cls,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
        organizer: OrganizerProvider | None = None,
        transcript_reviews: TranscriptReviewProvider | None = None,
        transcripts: TranscriptProvider | None = None,
    ) -> FastAPI:
        projectkoios_app = cls(
            configuration=configuration,
            services=services,
            github_tasks=github_tasks,
            organizer=organizer,
            transcript_reviews=transcript_reviews,
            transcripts=transcripts,
        )
        return projectkoios_app.app
