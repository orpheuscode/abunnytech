"""One-command demo launcher for the abunnytech pipeline.

Starts:
  1. State CRUD API   (port 8000) — with demo seed data
  2. Control Plane    (port 8001) — stage routers + /pipeline/demo
  3. Dashboard        (port 8501) — Flask owner UI (API keys + pipeline views)

Usage:
    uv run python scripts/demo.py
    uv run python scripts/demo.py --no-dashboard
    uv run python scripts/demo.py --seed-only

Ctrl+C stops all services.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from runtime_dashboard.secrets_store import read_for_subprocess

REPO = Path(__file__).resolve().parent.parent


def _env() -> dict[str, str]:
    env = {**os.environ}
    python_path = str(REPO)
    if "PYTHONPATH" in env:
        python_path = f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = python_path
    env.setdefault("SEED_ON_STARTUP", "true")
    env.setdefault("DRY_RUN", "true")
    env.setdefault("FEATURE_STAGE5_MONETIZE", "false")
    for k, v in read_for_subprocess().items():
        if v:
            env[k] = v
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="abunnytech demo launcher")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip Flask owner dashboard")
    parser.add_argument("--seed-only", action="store_true", help="Seed DB and exit")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--cp-port", type=int, default=8001)
    parser.add_argument("--dash-port", type=int, default=8501)
    args = parser.parse_args()

    env = _env()
    procs: list[subprocess.Popen] = []

    def cleanup(sig=None, frame=None) -> None:
        print("\nShutting down services...")
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 60)
    print(" abunnytech Demo Launcher")
    print("=" * 60)

    # 1. API server
    print(f"\n  Starting State CRUD API on port {args.api_port}...")
    api_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "state_api.main:app",
            "--host", "0.0.0.0",
            "--port", str(args.api_port),
        ],
        cwd=str(REPO),
        env=env,
    )
    procs.append(api_proc)
    time.sleep(2)

    if args.seed_only:
        print("  Seed mode — waiting for startup then exiting.")
        time.sleep(3)
        cleanup()
        return

    # 2. Control plane
    print(f"  Starting Control Plane on port {args.cp_port}...")
    cp_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "services.control_plane.app:app",
            "--host", "0.0.0.0",
            "--port", str(args.cp_port),
        ],
        cwd=str(REPO),
        env=env,
    )
    procs.append(cp_proc)
    time.sleep(2)

    # 3. Dashboard
    if not args.no_dashboard:
        print(f"  Starting Dashboard on port {args.dash_port}...")
        dash_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runtime_dashboard.flask_owner_app",
            ],
            cwd=str(REPO),
            env={**env, "DASHBOARD_PORT": str(args.dash_port)},
        )
        procs.append(dash_proc)

    print("\n" + "=" * 60)
    print("  Services running:")
    print(f"    API:         http://localhost:{args.api_port}")
    print(f"    API docs:    http://localhost:{args.api_port}/docs")
    print(f"    Control:     http://localhost:{args.cp_port}")
    print(f"    Demo trigger: POST http://localhost:{args.cp_port}/pipeline/demo")
    if not args.no_dashboard:
        print(f"    Dashboard:   http://localhost:{args.dash_port}")
    print(f"\n  Dry-run: {env.get('DRY_RUN', 'true')}")
    print(f"  Stage 5: {env.get('FEATURE_STAGE5_MONETIZE', 'false')}")
    print("=" * 60)
    print("\n  Press Ctrl+C to stop all services.\n")

    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"  WARNING: Process {p.args} exited with code {p.returncode}")
            time.sleep(5)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
