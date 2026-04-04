#!/usr/bin/env python3
"""Minimal HTTP smoke test for stages 0–2 (no pytest)."""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke-test Creator Pipeline API")
    p.add_argument(
        "--base-url",
        default=os.environ.get("PIPELINE_API_BASE", "http://127.0.0.1:8000"),
        help="API base (or set PIPELINE_API_BASE)",
    )
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(timeout=120.0) as client:
        h = client.get(f"{base}/health")
        h.raise_for_status()
        print("health:", h.json())

        cr = client.post(f"{base}/runs")
        cr.raise_for_status()
        run_id = cr.json()["run_id"]
        print("run_id:", run_id)

        r0 = client.post(
            f"{base}/runs/{run_id}/stage0",
            json={
                "display_name": "Smoke",
                "niche": "testing",
                "tone": "dry",
                "topics": ["smoke"],
            },
        )
        r0.raise_for_status()
        print("stage0: identity_matrix.matrix_id =", r0.json()["identity_matrix"].get("matrix_id"))

        r1 = client.post(f"{base}/runs/{run_id}/stage1")
        r1.raise_for_status()
        print("stage1: blueprint_id =", r1.json()["video_blueprint"].get("blueprint_id"))

        r2 = client.post(f"{base}/runs/{run_id}/stage2")
        r2.raise_for_status()
        cp = r2.json()["content_package"]
        print("stage2: package_id =", cp.get("package_id"))

        art = client.get(f"{base}/runs/{run_id}/artifacts")
        art.raise_for_status()
        keys = sorted(art.json().keys())
        print("artifacts keys:", keys)

    print("smoke_test_api: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as e:
        print("smoke_test_api: FAILED", e, file=sys.stderr)
        raise SystemExit(1) from e
