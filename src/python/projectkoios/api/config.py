from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from projectkoios.obsidian.config import VaultConfiguration

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DeploymentProfile(StrEnum):
    PUBLIC = "public"
    CONTROL = "control"


@dataclass(frozen=True)
class DatabaseConfiguration:
    path: Path | None = None


@dataclass(frozen=True)
class CitationReviewConfiguration:
    bundle_path: Path = field(
        default_factory=lambda: (
            Path.home()
            / ".local/share/projectkoios/citation-review/bundle.json"
        )
    )
    decisions_path: Path = field(
        default_factory=lambda: (
            Path.home()
            / ".local/share/projectkoios/citation-review/decisions.sqlite3"
        )
    )
    sources_root: Path = field(
        default_factory=lambda: (
            Path.home() / "projectkoios/assets/references/ksdft2effmass"
        )
    )


@dataclass(frozen=True)
class LiteratureReviewConfiguration:
    run_path: Path | None = field(
        default_factory=lambda: _configured_literature_review_run()
    )


@dataclass(frozen=True)
class PublicationConfiguration:
    catalog_path: Path | None = field(
        default_factory=lambda: _configured_publication_catalog()
    )


@dataclass(frozen=True)
class GitHubConfiguration:
    repositories: tuple[str, ...] = field(
        default_factory=lambda: _configured_github_repositories()
    )
    executable: str = field(default_factory=lambda: _configured_github_cli())


@dataclass(frozen=True)
class ProjectKoiosAppConfiguration:
    title: str = "Project Koios"
    version: str = "0.0.0"
    debug: bool = False
    deployment_profile: DeploymentProfile = field(
        default_factory=lambda: _configured_deployment_profile()
    )

    vault: VaultConfiguration = field(default_factory=VaultConfiguration)
    database: DatabaseConfiguration = field(
        default_factory=DatabaseConfiguration
    )
    citation_review: CitationReviewConfiguration = field(
        default_factory=CitationReviewConfiguration
    )
    literature_review: LiteratureReviewConfiguration = field(
        default_factory=LiteratureReviewConfiguration
    )
    publications: PublicationConfiguration = field(
        default_factory=PublicationConfiguration
    )
    github: GitHubConfiguration = field(default_factory=GitHubConfiguration)


def _configured_deployment_profile() -> DeploymentProfile:
    raw_profile = os.environ.get("KOIOS_DEPLOYMENT_PROFILE", "public")
    try:
        return DeploymentProfile(raw_profile)
    except ValueError as error:
        choices = ", ".join(profile.value for profile in DeploymentProfile)
        raise ValueError(
            f"KOIOS_DEPLOYMENT_PROFILE must be one of: {choices}"
        ) from error


def _configured_publication_catalog() -> Path | None:
    catalog_path = os.environ.get("KOIOS_PUBLICATION_CATALOG")
    if catalog_path is None:
        return None
    return Path(catalog_path).expanduser()


def _configured_github_repositories() -> tuple[str, ...]:
    raw_repositories = os.environ.get("KOIOS_GITHUB_REPOSITORIES", "")
    if not raw_repositories:
        return ()
    repositories = tuple(
        repository.strip() for repository in raw_repositories.split(",")
    )
    if any(not repository for repository in repositories):
        raise ValueError("KOIOS_GITHUB_REPOSITORIES contains an empty identity")
    if len(repositories) > 20:
        raise ValueError(
            "KOIOS_GITHUB_REPOSITORIES is limited to 20 identities"
        )
    if len(repositories) != len(set(repositories)):
        raise ValueError("KOIOS_GITHUB_REPOSITORIES contains a duplicate")
    return repositories


def _configured_github_cli() -> str:
    executable = os.environ.get("KOIOS_GITHUB_CLI", "gh").strip()
    if not executable or len(executable) > 4096:
        raise ValueError("KOIOS_GITHUB_CLI must name one executable")
    return executable


def _configured_literature_review_run() -> Path | None:
    explicit_run = os.environ.get("KOIOS_LITERATURE_REVIEW_RUN")
    if explicit_run:
        return Path(explicit_run).expanduser()

    config_path = Path(
        os.environ.get(
            "KOIOS_CONFIG",
            "~/.config/projectkoios/config.toml",
        )
    ).expanduser()
    try:
        with config_path.open("rb") as stream:
            configuration = tomllib.load(stream)
    except OSError, tomllib.TOMLDecodeError:
        return None

    data_root_raw = os.environ.get("KOIOS_DATA_ROOT")
    if data_root_raw is None:
        configured_root = configuration.get("data_root")
        if not isinstance(configured_root, str) or not configured_root:
            return None
        data_root_raw = configured_root

    literature_review = configuration.get("literature_review")
    if not isinstance(literature_review, dict):
        return None
    run_id = literature_review.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        return None
    return Path(data_root_raw).expanduser() / "state" / "runs" / run_id
