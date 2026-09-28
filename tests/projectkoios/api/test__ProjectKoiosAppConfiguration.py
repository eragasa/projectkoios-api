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


def test__equation_review__requires_explicit_complete_pizzi_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE",
        "/private/pizzi2020/bundle.json",
    )
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS",
        "/private/pizzi2020/regions",
    )

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.equation_review.pizzi2020 is not None
    assert configuration.equation_review.pizzi2020.bundle_path == Path(
        "/private/pizzi2020/bundle.json"
    )
    assert configuration.equation_review.pizzi2020.regions_root == Path(
        "/private/pizzi2020/regions"
    )


def test__equation_review__rejects_partial_pizzi_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE",
        "/private/pizzi2020/bundle.json",
    )
    monkeypatch.delenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="pizzi2020 equation review requires both",
    ):
        ProjectKoiosAppConfiguration()


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
