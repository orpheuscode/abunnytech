"""Feature flag system. Simple but extensible."""

from packages.shared.config import get_settings


def is_enabled(flag_name: str) -> bool:
    settings = get_settings()
    attr = f"feature_{flag_name}"
    return getattr(settings, attr, False)


def is_dry_run() -> bool:
    return get_settings().dry_run
