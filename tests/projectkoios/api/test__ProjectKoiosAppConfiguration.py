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
