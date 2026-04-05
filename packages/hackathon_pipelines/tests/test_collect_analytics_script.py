from __future__ import annotations

import csv
from pathlib import Path

from scripts.collect_analytics import run_demo

from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore


def test_collect_analytics_demo_persists_all_scheduled_snapshots_and_exports_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "analytics_demo.sqlite3"
    csv_path = tmp_path / "analytics_demo.csv"

    result = run_demo(db_path=db_path, csv_path=csv_path)

    store = SQLiteHackathonStore(db_path)
    snapshots = store.list_snapshots()
    assert [snapshot.scheduled_check for snapshot in snapshots] == ["day_1", "day_3", "week_1"]
    assert [snapshot.views for snapshot in snapshots] == [2_400, 8_900, 24_500]
    assert snapshots[-1].likes == 1_800
    assert snapshots[-1].retention_curve_pct["1"] == 88
    assert snapshots[-1].retention_curve_pct["5"] == 52
    assert "pattern interrupt" in (snapshots[-1].adaptation_recommendation or "")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3
    assert rows[0]["scheduled_check"] == "day_1"
    assert rows[1]["views"] == "8900"
    assert rows[2]["follows_gained"] == "34"
    assert rows[2]["retention_1s_pct"] == "88"
    assert rows[2]["retention_5s_pct"] == "52"
    assert "mid-content retention falls to 52% by 5 seconds" in rows[2]["retention_takeaway"]
    assert result.csv_path == str(csv_path.resolve())
