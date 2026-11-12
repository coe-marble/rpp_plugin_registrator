"""Version information written to plugin-library registration manifests."""

from __future__ import annotations

from rpp_plugin_registrator import __version__


def current_registrator_version() -> str:
    """Return the version of the registrator code currently being executed."""
    return __version__


def release_version(value: str | None) -> tuple[int, ...] | None:
    """Return a numeric release version, or None for unknown/non-release versions."""
    if not value:
        return None
    parts = value.split(".")
    if not parts or any(not part.isdecimal() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer_version(current: str, recorded: str | None) -> bool:
    """Whether a numeric installed release is newer than the recorded release."""
    current_release = release_version(current)
    recorded_release = release_version(recorded)
    return (
        current_release is not None
        and recorded_release is not None
        and current_release > recorded_release
    )
