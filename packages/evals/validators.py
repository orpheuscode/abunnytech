"""
Contract validation helpers for m2t4 black-box tests.

These check that a model instance satisfies the structural requirements
expected by its downstream consumer, without importing the consumer's code.
"""
from __future__ import annotations

from pydantic import BaseModel


def assert_contract_valid(instance: BaseModel, required_fields: list[str]) -> None:
    """Assert that all required fields are present and non-None on the instance."""
    for field in required_fields:
        value = getattr(instance, field, None)
        assert value is not None, (
            f"{type(instance).__name__} missing required field '{field}' "
            f"(got {value!r})"
        )


def assert_no_live_credentials(env: dict[str, str]) -> None:
    """
    Assert that none of the known live-credential env vars are set.

    Ensures smoke test doesn't accidentally use real platform tokens.
    """
    credential_keys = [
        "TIKTOK_ACCESS_TOKEN",
        "TIKTOK_OPEN_ID",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_ACCOUNT_ID",
        "SHOPIFY_STORE_DOMAIN",
        "SHOPIFY_ADMIN_TOKEN",
    ]
    found = [k for k in credential_keys if env.get(k)]
    assert not found, (
        f"Live credentials detected in environment: {found}. "
        "Smoke test must run without live credentials."
    )


def assert_feature_flag_off(env: dict[str, str], flag_key: str = "STAGE5_MONETIZE_ENABLED") -> None:
    """Assert that a feature flag env var is not truthy."""
    raw = env.get(flag_key, "false").lower()
    assert raw not in ("1", "true", "yes", "on"), (
        f"Feature flag {flag_key}={raw!r} is enabled — "
        "Stage 5 must be gated by this flag in the smoke path."
    )


def assert_dry_run_records(records: list, record_type: str = "DistributionRecord") -> None:
    """Assert that all records in a list are dry-run records."""
    for r in records:
        dry = getattr(r, "dry_run", None)
        assert dry is True, (
            f"{record_type} record_id={getattr(r, 'record_id', '?')} "
            f"has dry_run={dry!r}; expected True in smoke run."
        )
