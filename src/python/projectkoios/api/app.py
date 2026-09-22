from __future__ import annotations

from fastapi import FastAPI
from projectkoios.api.citation_review import CitationReviewRepository
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)
from projectkoios.api.github_tasks import GitHubTaskReader
from projectkoios.api.literature_review import LiteratureReviewRepository
from projectkoios.api.publications import PublicationRepository
from projectkoios.api.routers.citation_review import (
    create_citation_review_router,
)
from projectkoios.api.routers.core import create_core_router
from projectkoios.api.routers.github_tasks import (
    GitHubTaskProvider,
    create_github_tasks_router,
)
from projectkoios.api.routers.literature_review import (
    create_literature_review_router,
)
from projectkoios.api.routers.publications import create_publications_router
from projectkoios.api.routers.search import create_search_router
from projectkoios.runtime import ProjectKoiosServices, create_services


class ProjectKoiosApp:
    def __init__(
        self,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
    ) -> None:
        self.configuration = configuration or ProjectKoiosAppConfiguration()
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
        self.app.include_router(create_publications_router(self.publications))

        if self.configuration.deployment_profile is DeploymentProfile.CONTROL:
            self._register_control_routes(services, github_tasks)

    def _register_control_routes(
        self,
        services: ProjectKoiosServices | None,
        github_tasks: GitHubTaskProvider | None,
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

    @classmethod
    def create_app(
        cls,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
        github_tasks: GitHubTaskProvider | None = None,
    ) -> FastAPI:
        projectkoios_app = cls(
            configuration=configuration,
            services=services,
            github_tasks=github_tasks,
        )
        return projectkoios_app.app
