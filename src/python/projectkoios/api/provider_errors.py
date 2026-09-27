from __future__ import annotations


class ProviderUnavailable(RuntimeError):
    """An injected owner adapter cannot currently supply its projection."""


class ProjectionNotFound(LookupError):
    """An owner adapter has no projection for the requested identity."""
