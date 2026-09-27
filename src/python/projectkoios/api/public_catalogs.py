from __future__ import annotations

from projectkoios.api.course_models import PublicCourseCatalog
from projectkoios.api.project_models import PublicProjectCatalog


class EmptyPublicCourseProvider:
    """Explicit empty projection used when no owner adapter is injected."""

    def list_courses(self) -> PublicCourseCatalog:
        return PublicCourseCatalog()


class EmptyPublicProjectProvider:
    """Explicit empty projection used when no owner adapter is injected."""

    def list_projects(self) -> PublicProjectCatalog:
        return PublicProjectCatalog()
