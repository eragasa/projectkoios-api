from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_mypy(path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PROJECTKOIOS_COURSE_REFERENCE_ARCHITECTURE_TARGETS"] = str(
        path
    )
    return subprocess.run(
        (
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--no-incremental",
            str(path),
        ),
        cwd=Path(__file__).parents[3],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("source", "diagnostic", "name"),
    [
        (
            "class _PrivateError(RuntimeError):\n    pass\n",
            "private classes are prohibited",
            "private.py",
        ),
        (
            "class PublicError(RuntimeError):\n"
            "    class NestedError(RuntimeError):\n"
            "        pass\n",
            "nested class 'NestedError' is prohibited",
            "nested.py",
        ),
        (
            "class AuthorityProvider(RuntimeError):\n    pass\n",
            "multi-action class role is prohibited",
            "provider.py",
        ),
        (
            "from projectkoios.base import DataObjectActionizer\n"
            "class ReadActionizer(DataObjectActionizer[object, object]):\n"
            "    __slots__ = ()\n"
            "    def action(self, *, request: object) -> object:\n"
            "        return request\n"
            "    def refresh(self) -> None:\n"
            "        return None\n",
            "Actionizer may expose only __init__ and action",
            "multi_action.py",
        ),
        (
            "def public_helper() -> None:\n    return None\n",
            "module function 'public_helper' must be private",
            "public_helper.py",
        ),
        (
            "from package.module import _private\n",
            "cross-module private imports are prohibited",
            "private_import.py",
        ),
        (
            "class FactoryError(RuntimeError):\n"
            "    @classmethod\n"
            "    def create(cls) -> 'FactoryError':\n"
            "        return cls()\n",
            "class/static factories are prohibited",
            "factory.py",
        ),
        (
            "from dataclasses import dataclass\n"
            "from projectkoios.base import DataObjectModel\n"
            "@dataclass\n"
            "class MutableData(DataObjectModel):\n"
            "    value: str\n",
            "passive data must be a frozen, slotted dataclass",
            "mutable_data.py",
        ),
        (
            "from dataclasses import dataclass\n"
            "from projectkoios.base import DataObjectModel\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class PassiveData(DataObjectModel):\n"
            "    value: str\n"
            "    def refresh(self) -> str:\n"
            "        return self.value\n",
            "passive data may define only invariant validation",
            "operational_data.py",
        ),
        (
            "from pydantic import BaseModel\n"
            "class BoundaryModel(BaseModel):\n"
            "    value: str\n",
            "Pydantic boundary models must be frozen",
            "mutable_model.py",
        ),
        (
            "AUTHORITY_REGISTRY: dict[str, object] = {}\n",
            "dynamic or central registries are prohibited",
            "registry.py",
        ),
        (
            "class WrongActionizer(RuntimeError):\n    pass\n",
            "Actionizer names and DataObjectActionizer inheritance must agree",
            "wrong_actionizer.py",
        ),
        (
            '"""Package marker."""\nVALUE = 1\n',
            "package initializers must be docstring-only",
            "__init__.py",
        ),
    ],
)
def test__architecture_plugin_rejects_prohibited_shapes(
    tmp_path: Path,
    source: str,
    diagnostic: str,
    name: str,
) -> None:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")

    completed = _run_mypy(target)

    assert completed.returncode != 0
    assert diagnostic in completed.stderr + completed.stdout
    assert "[course-reference-architecture]" in (
        completed.stderr + completed.stdout
    )


def test__architecture_plugin_accepts_private_pure_module_helpers(
    tmp_path: Path,
) -> None:
    target = tmp_path / "accepted.py"
    target.write_text(
        "def _normalized(value: str) -> str:\n    return value.strip()\n",
        encoding="utf-8",
    )

    completed = _run_mypy(target)

    assert completed.returncode == 0, completed.stderr + completed.stdout
