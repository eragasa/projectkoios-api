from __future__ import annotations

import re
from typing import Any

from pydantic_core import core_schema

MAX_COUNT = 1_000_000_000
MAX_BINARY_SIZE = 1_000_000_000_000
MAX_REGION_COORDINATE = 1_000_000.0
MAX_OPAQUE_ID_LENGTH = 256
MAX_RELATIVE_PATH_LENGTH = 4096

_OPAQUE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
_OPAQUE_ID = re.compile(_OPAQUE_ID_PATTERN)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")


class OpaqueId(str):
    """A bounded path-free identity projected by an owning domain."""

    def __new__(cls, value: str) -> OpaqueId:
        cls._check(value)
        return str.__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any,
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(
                min_length=1,
                max_length=MAX_OPAQUE_ID_LENGTH,
                pattern=_OPAQUE_ID_PATTERN,
                strict=True,
            ),
        )

    @classmethod
    def _validate(cls, value: str) -> OpaqueId:
        return cls(value)

    @classmethod
    def _check(cls, value: str) -> None:
        if (
            not 1 <= len(value) <= MAX_OPAQUE_ID_LENGTH
            or _OPAQUE_ID.fullmatch(value) is None
            or ".." in value
            or (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
        ):
            raise ValueError("opaque identities cannot contain path syntax")


class SafeRelativePosixPath(str):
    """A normalized relative POSIX display path, never a filesystem path."""

    def __new__(cls, value: str) -> SafeRelativePosixPath:
        cls._check(value)
        return str.__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any,
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(
                min_length=1,
                max_length=MAX_RELATIVE_PATH_LENGTH,
                strict=True,
            ),
        )

    @classmethod
    def _validate(cls, value: str) -> SafeRelativePosixPath:
        return cls(value)

    @classmethod
    def _check(cls, value: str) -> None:
        segments = value.split("/")
        if (
            not 1 <= len(value) <= MAX_RELATIVE_PATH_LENGTH
            or value.startswith("/")
            or "\\" in value
            or _CONTROL_CHARACTER.search(value) is not None
            or any(segment in {"", ".", ".."} for segment in segments)
        ):
            raise ValueError("path must be a normalized relative POSIX path")
