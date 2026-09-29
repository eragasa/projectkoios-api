from __future__ import annotations

from collections.abc import Callable

from projectkoios.api.provider_errors import (
    ProjectionNotFound,
    ProviderUnavailable,
)
from pydantic import BaseModel, ValidationError


class MalformedProviderProjection(ValueError):
    """An owner adapter supplied data outside its declared API contract."""


class UnexpectedProviderFailure(RuntimeError):
    """An owner adapter failed without a declared availability condition."""


def invoke_provider[ValueT](call: Callable[[], ValueT]) -> ValueT:
    """Call a provider without catching cancellation or other base exits."""

    try:
        return call()
    except ProjectionNotFound, ProviderUnavailable:
        raise
    except ValidationError as error:
        raise MalformedProviderProjection from error
    except Exception as error:
        raise UnexpectedProviderFailure from error


def validated_provider_projection[ProjectionT: BaseModel](
    call: Callable[[], object],
    model: type[ProjectionT],
) -> ProjectionT:
    """Return a fresh, strictly validated API model for provider output."""

    value = invoke_provider(call)
    try:
        payload = (
            value.model_dump(
                mode="python",
                round_trip=True,
                warnings=False,
            )
            if isinstance(value, BaseModel)
            else value
        )
        return model.model_validate(payload, strict=True)
    except ValidationError as error:
        raise MalformedProviderProjection from error
    except Exception as error:
        raise UnexpectedProviderFailure from error
