from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from projectkoios.api.app import ProjectKoiosApp
from projectkoios.api.config import (
    DeploymentProfile,
    ProjectKoiosAppConfiguration,
)

_DEFAULT_OUTPUT = Path("openapi/control.openapi.json")


def combined_openapi_schema() -> dict[str, Any]:
    """Generate the authoritative public-plus-control OpenAPI document."""

    app = ProjectKoiosApp.create_app(
        configuration=ProjectKoiosAppConfiguration(
            title="Project Koios",
            version="0.0.0",
            debug=False,
            deployment_profile=DeploymentProfile.CONTROL,
        )
    )
    return app.openapi()


def combined_openapi_bytes() -> bytes:
    document = json.dumps(
        combined_openapi_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{document}\n".encode()


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic combined API contract."
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(arguments)
    expected = combined_openapi_bytes()

    if options.check:
        try:
            observed = options.output.read_bytes()
        except OSError:
            return 1
        return 0 if observed == expected else 1

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
