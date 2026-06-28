from dataclasses import dataclass, field
from pathlib import Path

from projectkoios.obsidian.config import VaultConfiguration


@dataclass(frozen=True)
class DatabaseConfiguration:
    path: Path | None = None


@dataclass(frozen=True)
class ProjectKoiosAppConfiguration:
    title: str = "Project Koios"
    version: str = "0.0.0"
    debug: bool = True

    vault: VaultConfiguration \
        = field(default_factory=VaultConfiguration)
    database: DatabaseConfiguration \
        = field(default_factory=DatabaseConfiguration)
