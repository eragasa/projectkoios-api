from pathlib import Path

import pytest
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
    ProjectReferenceIntakeConfiguration,
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


def test__equation_review__reads_one_explicit_document_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT",
        "/private/pizzi2020/document",
    )

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.equation_review.pizzi2020 is not None
    assert configuration.equation_review.pizzi2020.document_root == Path(
        "/private/pizzi2020/document"
    )


def test__equation_review__has_no_default_or_legacy_bundle_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT",
        raising=False,
    )
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE",
        "/obsolete/bundle.json",
    )
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS",
        "/obsolete/regions",
    )

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.equation_review.pizzi2020 is None


def test__equation_review__rejects_empty_explicit_document_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT",
        "",
    )

    with pytest.raises(
        ValueError,
        match="KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT must not be empty",
    ):
        ProjectKoiosAppConfiguration()


def test__transcripts__read_one_explicit_document_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_TRANSCRIPT_DOCUMENT_ROOT",
        "~/koios/transcripts/document",
    )

    configuration = ProjectKoiosAppConfiguration()

    assert (
        configuration.transcripts.document_root
        == Path("~/koios/transcripts/document").expanduser()
    )


def test__transcripts__have_no_default_document_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KOIOS_TRANSCRIPT_DOCUMENT_ROOT", raising=False)

    configuration = ProjectKoiosAppConfiguration()

    assert configuration.transcripts.document_root is None


def test__transcripts__reject_an_empty_document_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_TRANSCRIPT_DOCUMENT_ROOT", "")

    with pytest.raises(
        ValueError,
        match="KOIOS_TRANSCRIPT_DOCUMENT_ROOT must not be empty",
    ):
        ProjectKoiosAppConfiguration()


def test__project_reference_intake__reads_explicit_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_PROJECT_REFERENCE_DATABASE_ROOT",
        "~/koios/project-references/database",
    )
    monkeypatch.setenv(
        "KOIOS_PROJECT_REFERENCE_OBJECT_ROOT",
        "~/koios/project-references/objects",
    )
    monkeypatch.setenv(
        "KOIOS_PROJECT_REFERENCE_DATABASE_NAME",
        "ksdft2effmass.sqlite3",
    )
    monkeypatch.setenv("KOIOS_PROJECT_REFERENCE_MAX_PDF_BYTES", "4096")

    intake = ProjectKoiosAppConfiguration().project_reference_intake

    assert (
        intake.database_root
        == Path("~/koios/project-references/database").expanduser()
    )
    assert (
        intake.object_root
        == Path("~/koios/project-references/objects").expanduser()
    )
    assert intake.database_name == "ksdft2effmass.sqlite3"
    assert intake.max_pdf_bytes == 4096


def test__project_reference_intake__requires_both_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOIOS_PROJECT_REFERENCE_DATABASE_ROOT",
        "~/koios/project-references/database",
    )
    monkeypatch.delenv("KOIOS_PROJECT_REFERENCE_OBJECT_ROOT", raising=False)

    with pytest.raises(
        ValueError,
        match="database and object roots must be set together",
    ):
        ProjectKoiosAppConfiguration()


@pytest.mark.parametrize(
    ("database_name", "max_pdf_bytes"),
    [
        ("../references.sqlite3", 4096),
        ("references.db", 4096),
        ("references.sqlite3", 0),
        ("references.sqlite3", 100_000_001),
    ],
)
def test__project_reference_intake__rejects_invalid_bounds(
    database_name: str,
    max_pdf_bytes: int,
) -> None:
    with pytest.raises(ValueError):
        ProjectReferenceIntakeConfiguration(
            database_name=database_name,
            max_pdf_bytes=max_pdf_bytes,
        )


def test__project_reference_intake__rejects_noninteger_environment_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_PROJECT_REFERENCE_MAX_PDF_BYTES", "many")

    with pytest.raises(
        ValueError,
        match="KOIOS_PROJECT_REFERENCE_MAX_PDF_BYTES must be an integer",
    ):
        ProjectKoiosAppConfiguration()


def test__course_catalog__reads_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOIOS_COURSE_CATALOG", "~/koios/courses.json")

    configuration = ProjectKoiosAppConfiguration()

    assert (
        configuration.courses.catalog_path
        == Path("~/koios/courses.json").expanduser()
    )


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
