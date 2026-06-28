# dev/spike_fastapi_app_boundary/tests/app/test__ProjectKoiosApp.py

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from projectkoios.api.app import ProjectKoiosApp  # noqa: E402
from projectkoios.api.config import ProjectKoiosAppConfiguration  # noqa: E402


@dataclass(frozen=True)
class CreateAppCase:
    """
    Test case for ProjectKoiosApp.create_app().

    Each case supplies either no configuration or an explicit
    ProjectKoiosAppConfiguration.
    """

    configuration: ProjectKoiosAppConfiguration | None

    @property
    def expected(self) -> ProjectKoiosAppConfiguration:
        """
        Return the configuration that the created FastAPI app should use.

        If the test case provides a configuration, that configuration is the
        expected source of app metadata. If the test case provides None, the
        app should construct and use the default ProjectKoiosAppConfiguration.
        """

        return self.configuration or ProjectKoiosAppConfiguration()


CREATE_APP_CASES = [
    # Case 1:
    # No configuration is supplied. The app should fall back to the default
    # ProjectKoiosAppConfiguration.
    CreateAppCase(
        configuration=None,
    ),
    # Case 2:
    # A custom configuration is supplied. The created FastAPI app should use
    # these exact values.
    CreateAppCase(
        configuration=ProjectKoiosAppConfiguration(
            title="Custom Project Koios",
            version="1.2.3",
            debug=False,
        ),
    ),
]


def test__create_app__returns_fastapi_app() -> None:
    """
    ProjectKoiosApp.create_app() should return the ASGI application object.

    Uvicorn needs a FastAPI/ASGI app object. This test verifies that the
    class-level app factory produces that object.
    """

    app = ProjectKoiosApp.create_app()

    assert isinstance(app, FastAPI)


@pytest.mark.parametrize("case", CREATE_APP_CASES)
def test__create_app__uses_configuration(
    case: CreateAppCase,
) -> None:
    """
    ProjectKoiosApp.create_app() should configure the FastAPI app metadata.

    This test covers both construction paths:

    - configuration=None
    - configuration=ProjectKoiosAppConfiguration(...)

    The FastAPI app should receive its title, version, and debug flag from
    the expected ProjectKoiosAppConfiguration object.
    """

    app = ProjectKoiosApp.create_app(configuration=case.configuration)

    assert app.title == case.expected.title
    assert app.version == case.expected.version
    assert app.debug is case.expected.debug