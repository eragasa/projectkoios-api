"""Strict mypy plugin for the course-reference HTTP architecture slice."""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

from mypy.nodes import IndexExpr, RefExpr
from mypy.options import Options
from mypy.plugin import ClassDefContext, Plugin

_RULE: Final = "course-reference-architecture"
_DEFAULT_GLOBS: Final = (
    "src/python/projectkoios/api/course_reference_authority*.py",
    "src/python/projectkoios/api/course_reference_authority/**/*.py",
    "src/python/projectkoios/api/routers/course_reference_authority.py",
    "tests/projectkoios/api/test__CourseReferenceA*.py",
    "tests/projectkoios/api/routers/"
    "test__create_course_reference_authority_router.py",
)
_FORBIDDEN_CLASS_TERMS: Final = (
    "Provider",
    "Service",
    "Manager",
    "Repository",
    "Facade",
    "Helper",
)
_FACTORY_PREFIXES: Final = (
    "build",
    "create",
    "factory",
    "from_",
    "load",
    "make",
    "new",
    "open",
)
_DATA_BASES: Final = {
    "DataObjectModel",
    "DataObjectActionRequest",
    "DataObjectActionResult",
}
_MODEL_BASES: Final = {"BaseModel", "StrictModel", "RequestModel"}
_ENUM_BASES: Final = {"Enum", "IntEnum", "StrEnum"}
_ERROR_BASES: Final = {"BaseException", "Exception", "RuntimeError"}
_PROTOCOL_BASES: Final = {"Protocol"}


class CourseReferenceArchitecturePlugin(Plugin):
    """Fail normal mypy startup when the bounded slice violates its shape."""

    def __init__(self, options: Options) -> None:
        super().__init__(options)
        violations = tuple(
            violation
            for target in _target_paths()
            for violation in _check_path(target)
        )
        if violations:
            for violation in violations:
                print(violation, file=sys.stderr)
            raise SystemExit(1)

    def get_customize_class_mro_hook(
        self,
        fullname: str,
    ) -> Callable[[ClassDefContext], None] | None:
        if fullname.startswith("projectkoios.api.course_reference_authority"):
            return _check_nominal_class
        return None


def plugin(version: str) -> type[CourseReferenceArchitecturePlugin]:
    """Return the plugin entry point required by mypy."""
    del version
    return CourseReferenceArchitecturePlugin


def _check_nominal_class(context: ClassDefContext) -> None:
    fullname = context.cls.fullname
    name = context.cls.name
    expected: set[str]
    if fullname.startswith(
        "projectkoios.api.course_reference_authority_models."
    ):
        if name in {"StrictModel", "RequestModel"}:
            expected = {"pydantic.main.BaseModel"}
        elif name.endswith("Request"):
            expected = {
                "projectkoios.api.course_reference_authority_models.RequestModel"
            }
        elif name.endswith("Response"):
            expected = {
                "projectkoios.api.course_reference_authority_models.StrictModel"
            }
        else:
            expected = {"enum.StrEnum"}
    elif name.endswith("Actionizer"):
        expected = {"projectkoios.base.DataObjectActionizer"}
    elif name.endswith("Request"):
        expected = {"projectkoios.base.DataObjectActionRequest"}
    elif name.endswith("Result"):
        expected = {"projectkoios.base.DataObjectActionResult"}
    elif name.endswith("Failure"):
        expected = {"builtins.RuntimeError"}
    else:
        expected = {"projectkoios.base.DataObjectModel"}
    observed = {
        base_fullname
        for expression in context.cls.base_type_exprs
        if (base_fullname := _semantic_base_fullname(expression))
    }
    if not observed & expected:
        context.api.fail(
            "course-reference class has a non-nominal direct base "
            f"(expected one of {sorted(expected)})",
            context.cls,
        )


def _semantic_base_fullname(expression: object) -> str:
    if isinstance(expression, IndexExpr):
        return _semantic_base_fullname(expression.base)
    if isinstance(expression, RefExpr):
        return expression.fullname
    return ""


def _target_paths() -> tuple[Path, ...]:
    configured = os.environ.get(
        "PROJECTKOIOS_COURSE_REFERENCE_ARCHITECTURE_TARGETS"
    )
    if configured is not None:
        return tuple(
            Path(item) for item in configured.split(os.pathsep) if item
        )
    return tuple(
        sorted(
            {
                path
                for pattern in _DEFAULT_GLOBS
                for path in Path().glob(pattern)
                if path.is_file()
            }
        )
    )


def _check_path(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return (_diagnostic(path, 1, "architecture target does not exist"),)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        line = error.lineno if isinstance(error, SyntaxError) else 1
        return (
            _diagnostic(path, line or 1, "architecture target is unreadable"),
        )
    class_bases = {
        node.name: tuple(_base_name(base) for base in node.bases)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    violations: list[str] = []
    if path.name == "__init__.py":
        statements = tree.body
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements = statements[1:]
        for statement in statements:
            violations.append(
                _diagnostic(
                    path,
                    statement.lineno,
                    "package initializers must be docstring-only",
                )
            )
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_private_import_violations(path, node))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            violations.extend(_class_violations(path, node, class_bases))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _allowed_module_function(path, node.name):
                violations.append(
                    _diagnostic(
                        path,
                        node.lineno,
                        f"module function {node.name!r} must be private",
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assignment_names(node):
                if "REGISTRY" in name.upper():
                    violations.append(
                        _diagnostic(
                            path,
                            node.lineno,
                            "dynamic or central registries are prohibited",
                        )
                    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.ClassDef):
                    violations.append(
                        _diagnostic(
                            path,
                            child.lineno,
                            f"nested class {child.name!r} is prohibited",
                        )
                    )
    return tuple(violations)


def _class_violations(
    path: Path,
    node: ast.ClassDef,
    class_bases: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    violations: list[str] = []
    if node.name.startswith("_"):
        violations.append(
            _diagnostic(path, node.lineno, "private classes are prohibited")
        )
    if any(term in node.name for term in _FORBIDDEN_CLASS_TERMS):
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                f"multi-action class role is prohibited: {node.name}",
            )
        )
    lineage = _lineage(node.name, class_bases)
    is_actionizer = "DataObjectActionizer" in lineage
    is_request = "DataObjectActionRequest" in lineage
    is_result = "DataObjectActionResult" in lineage
    is_data = bool(lineage & _DATA_BASES)
    is_model = bool(lineage & _MODEL_BASES)
    is_enum = bool(lineage & _ENUM_BASES)
    is_error = bool(lineage & _ERROR_BASES)
    is_protocol = bool(lineage & _PROTOCOL_BASES)
    if node.name.endswith("Actionizer") != is_actionizer:
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                "Actionizer names and DataObjectActionizer inheritance "
                "must agree",
            )
        )
    if node.name.endswith("Request") and not (is_request or is_model):
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                "Request must inherit a nominal request or Pydantic model base",
            )
        )
    if node.name.endswith("Result") and not is_result:
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                "Result must inherit DataObjectActionResult",
            )
        )
    if not any(
        (
            is_actionizer,
            is_data,
            is_model,
            is_enum,
            is_error,
            is_protocol,
        )
    ):
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                f"class {node.name!r} is outside the nominal type taxonomy",
            )
        )
    methods = tuple(
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    if is_actionizer:
        if {method.name for method in methods} - {"__init__", "action"}:
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "Actionizer may expose only __init__ and action",
                )
            )
        if "action" not in {method.name for method in methods}:
            violations.append(
                _diagnostic(path, node.lineno, "Actionizer must define action")
            )
        if not _declares_slots(node):
            violations.append(
                _diagnostic(
                    path, node.lineno, "Actionizer must declare __slots__"
                )
            )
    elif is_data and not is_model:
        if not _frozen_slotted_dataclass(node):
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "passive data must be a frozen, slotted dataclass",
                )
            )
        if {method.name for method in methods} - {"__post_init__"}:
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "passive data may define only invariant validation",
                )
            )
    elif is_model:
        if not _frozen_pydantic_model(node, lineage):
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "Pydantic boundary models must be frozen",
                )
            )
        if any(not _is_model_validator(method) for method in methods):
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "Pydantic boundary methods must be validators",
                )
            )
    elif is_error and {method.name for method in methods} - {"__init__"}:
        violations.append(
            _diagnostic(
                path,
                node.lineno,
                "error classes may define only __init__",
            )
        )
    elif is_protocol:
        if {method.name for method in methods} != {"action"}:
            violations.append(
                _diagnostic(
                    path,
                    node.lineno,
                    "action protocols must expose exactly action",
                )
            )
    elif is_enum and methods:
        violations.append(
            _diagnostic(path, node.lineno, "enum classes must be passive")
        )
    for method in methods:
        decorators = {_decorator_name(item) for item in method.decorator_list}
        if decorators & {
            "classmethod",
            "staticmethod",
        } and method.name.startswith(_FACTORY_PREFIXES):
            violations.append(
                _diagnostic(
                    path,
                    method.lineno,
                    "class/static factories are prohibited",
                )
            )
    return tuple(violations)


def _lineage(
    name: str,
    class_bases: dict[str, tuple[str, ...]],
    seen: frozenset[str] = frozenset(),
) -> set[str]:
    if name in seen:
        return set()
    bases = set(class_bases.get(name, ()))
    for base in tuple(bases):
        bases.update(_lineage(base, class_bases, seen | {name}))
    return bases


def _private_import_violations(
    path: Path,
    node: ast.Import | ast.ImportFrom,
) -> tuple[str, ...]:
    names = tuple(alias.name for alias in node.names)
    module_parts = (
        tuple((node.module or "").split("."))
        if isinstance(node, ast.ImportFrom)
        else ()
    )
    if any(
        name.split(".")[-1].startswith("_")
        and not name.split(".")[-1].startswith("__")
        for name in names
    ) or any(
        part.startswith("_") and not part.startswith("__")
        for part in module_parts
    ):
        return (
            _diagnostic(
                path,
                node.lineno,
                "cross-module private imports are prohibited",
            ),
        )
    return ()


def _allowed_module_function(path: Path, name: str) -> bool:
    if name.startswith("_"):
        return True
    if path.name.startswith("test__") and name.startswith("test__"):
        return True
    return (
        path.name == "course_reference_authority.py"
        and path.parent.name == "routers"
        and name == "create_course_reference_authority_router"
    )


def _frozen_slotted_dataclass(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if _decorator_name(decorator.func) != "dataclass":
            continue
        values = {
            item.arg: item.value
            for item in decorator.keywords
            if item.arg is not None
        }
        return _literal_true(values.get("frozen")) and _literal_true(
            values.get("slots")
        )
    return False


def _frozen_pydantic_model(
    node: ast.ClassDef,
    lineage: set[str],
) -> bool:
    if "StrictModel" in lineage or "RequestModel" in lineage:
        return True
    for item in node.body:
        if not isinstance(item, (ast.Assign, ast.AnnAssign)):
            continue
        if "model_config" not in _assignment_names(item):
            continue
        value = item.value
        if (
            not isinstance(value, ast.Call)
            or _base_name(value.func) != "ConfigDict"
        ):
            continue
        keywords = {
            keyword.arg: keyword.value
            for keyword in value.keywords
            if keyword.arg is not None
        }
        if _literal_true(keywords.get("frozen")):
            return True
    return False


def _is_model_validator(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    decorators = {_decorator_name(item) for item in method.decorator_list}
    return bool(decorators & {"field_validator", "model_validator"})


def _declares_slots(node: ast.ClassDef) -> bool:
    return any(
        "__slots__" in _assignment_names(item)
        for item in node.body
        if isinstance(item, (ast.Assign, ast.AnnAssign))
    )


def _literal_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return tuple(
        target.id for target in targets if isinstance(target, ast.Name)
    )


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _diagnostic(path: Path, line: int, message: str) -> str:
    return f"{path}:{line}: error: {message}  [{_RULE}]"
