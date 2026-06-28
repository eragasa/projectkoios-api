from __future__ import annotations

from dataclasses import dataclass

from projectkoios.api.config import ProjectKoiosAppConfiguration
from projectkoios.indexing import InMemoryChunkIndex
from projectkoios.obsidian.service import VaultService
from projectkoios.search.service import SearchService


@dataclass(frozen=True)
class ProjectKoiosServices:
    search: SearchService
    vault: VaultService


def create_services(
    configuration: ProjectKoiosAppConfiguration,
) -> ProjectKoiosServices:
    search_index = InMemoryChunkIndex()

    search_service = SearchService(
        search_index=search_index,
    )

    vault_service = VaultService(
        configuration=configuration.vault,
    )

    return ProjectKoiosServices(
        search=search_service,
        vault=vault_service,
    )
