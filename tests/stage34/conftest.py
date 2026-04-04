"""
Root-level pytest conftest for m2t4 cross-stage tests.

Provides shared fixtures consumed by tests/test_contracts.py and
tests/test_handoffs.py. Stage-specific fixtures stay in their own
conftest files (e.g. tests/stage4/conftest.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from packages.evals.fixtures import (
    make_content_package,
    make_identity,
    make_s3_distribution_record,
    make_video_blueprint,
    load_s4_distribution_records,
    adapt_s3_to_s4_distribution_record,
)
from agents.stage3_distribution.contracts import DistributionRecord as S3DistributionRecord
from agents.stage4_analytics.contracts import DistributionRecord as S4DistributionRecord
from agents.stage4_analytics.state_adapter import StateAdapter


# ---------------------------------------------------------------------------
# Stage 0 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def identity():
    return make_identity()


# ---------------------------------------------------------------------------
# Stage 2 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def video_blueprint():
    return make_video_blueprint()


@pytest.fixture
def content_package():
    return make_content_package()


# ---------------------------------------------------------------------------
# Stage 3 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def s3_distribution_record() -> S3DistributionRecord:
    return make_s3_distribution_record()


@pytest.fixture
def s3_distribution_record_posted() -> S3DistributionRecord:
    from agents.stage3_distribution.contracts import DistributionStatus, Platform
    from datetime import datetime, UTC
    return make_s3_distribution_record(
        status=DistributionStatus.POSTED,
        post_id="tt_real_abc123",
        platform=Platform.TIKTOK,
        dry_run=False,
        posted_at=datetime(2026, 4, 4, 18, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Stage 4 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def s4_distribution_records() -> list[S4DistributionRecord]:
    return load_s4_distribution_records()


@pytest.fixture
def s4_distribution_record_from_s3(s3_distribution_record: S3DistributionRecord) -> S4DistributionRecord:
    return adapt_s3_to_s4_distribution_record(s3_distribution_record)


@pytest.fixture
def tmp_state_adapter(tmp_path: Path) -> StateAdapter:
    return StateAdapter(db_path=str(tmp_path / "test_m2t4.db"))
