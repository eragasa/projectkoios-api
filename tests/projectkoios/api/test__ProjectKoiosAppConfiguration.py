from pathlib import Path

import pytest
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)


def test__deployment_profile__defaults_to_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KOIOS_DEPLOYMENT_PROFILE", raising=False)

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.deployment_profile is DeploymentProfile.PUBLIC


def test__deployment_profile__reads_control_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_DEPLOYMENT_PROFILE", "control")

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.deployment_profile is DeploymentProfile.CONTROL


def test__deployment_profile__rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_DEPLOYMENT_PROFILE", "private")

    with pytest.raises(
        ValueError,
        match="KOIOS_DEPLOYMENT_PROFILE must be one of: public, control",
    ):
        ProjectKoiosAppConfiguration()


def test__project_catalog__reads_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_PROJECT_CATALOG", "~/koios/projects.json")

    configuration = ProjectKoiosAppConfiguration()

    assert (
        configuration.projects.catalog_path
        == Path("~/koios/projects.json").expanduser()
    )


def test__github_repositories__parse_explicit_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_GITHUB_REPOSITORIES",
        "eragasa/projectkoios-api, eragasa/projectkoios-web",
    )

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.github.repositories == (
        "eragasa/projectkoios-api",
        "eragasa/projectkoios-web",
    )


def test__github_repositories__reject_duplicate_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_GITHUB_REPOSITORIES",
        "eragasa/projectkoios-api,eragasa/projectkoios-api",
    )

    with pytest.raises(
        ValueError,
        match="KOIOS_GITHUB_REPOSITORIES contains a duplicate",
    ):
        ProjectKoiosAppConfiguration()
