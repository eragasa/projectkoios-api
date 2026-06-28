from __future__ import annotations

from fastapi import FastAPI
from projectkoios.api.config import ProjectKoiosAppConfiguration
from projectkoios.api.routers.core import create_core_router
from projectkoios.api.routers.search import create_search_router
from projectkoios.runtime import ProjectKoiosServices, create_services


class ProjectKoiosApp:
    def __init__(
        self,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
    ) -> None:
        self.configuration = configuration or ProjectKoiosAppConfiguration()
        self.services = services or create_services(self.configuration)

        self.app = FastAPI(
            title=self.configuration.title,
            version=self.configuration.version,
            debug=self.configuration.debug,
        )

        self.register_routes()

    def register_routes(self) -> None:
        self.app.include_router(create_core_router())
        self.app.include_router(create_search_router(self.services.search))

    @classmethod
    def create_app(
        cls,
        configuration: ProjectKoiosAppConfiguration | None = None,
        services: ProjectKoiosServices | None = None,
    ) -> FastAPI:
        projectkoios_app = cls(
            configuration=configuration,
            services=services,
        )
        return projectkoios_app.app
