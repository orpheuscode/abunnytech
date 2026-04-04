from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(api_client: TestClient) -> None:
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_settings(api_client: TestClient) -> None:
    r = api_client.get("/settings")
    assert r.status_code == 200
    body = r.json()
    assert "dry_run" in body
    assert body["feature_stage5_enabled"] is False


def test_full_pipeline(api_client: TestClient) -> None:
    r = api_client.post("/runs")
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r0 = api_client.post(
        f"/runs/{run_id}/stage0",
        json={
            "display_name": "T",
            "niche": "testing",
            "tone": "dry",
            "topics": ["pytest"],
        },
    )
    assert r0.status_code == 200
    assert "identity_matrix" in r0.json()

    r1 = api_client.post(f"/runs/{run_id}/stage1")
    assert r1.status_code == 200
    assert "video_blueprint" in r1.json()

    r2 = api_client.post(f"/runs/{run_id}/stage2")
    assert r2.status_code == 200
    cp = r2.json()["content_package"]
    assert cp["run_id"] == run_id
    assert cp["primary_video"]["path"]

    art = api_client.get(f"/runs/{run_id}/artifacts")
    assert art.status_code == 200
    assert "content_package" in art.json()


def test_artifacts_404_unknown_run(api_client: TestClient) -> None:
    r = api_client.get("/runs/does-not-exist/artifacts")
    assert r.status_code == 404
