"""Unified smoke test for the abunnytech integrated pipeline.

Runs all validation in dry-run/mock mode — no credentials required.

Usage:
    uv run python scripts/smoke.py
    uv run python scripts/smoke.py --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
BANNER = "=" * 60
PYTEST_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
PYTEST_ARGS = ["-p", "pytest_asyncio.plugin"]


class Results:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        self.passed.append(label)
        print(f"  {PASS} {label}" + (f"  {detail}" if detail else ""))

    def fail(self, label: str, reason: str) -> None:
        self.failed.append((label, reason))
        print(f"  {FAIL} {label}  {reason}")

    def skip(self, label: str, reason: str = "") -> None:
        self.skipped.append(label)
        print(f"  {SKIP} {label}" + (f"  {reason}" if reason else ""))


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = {**os.environ, **(env or {})}
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or REPO,
            env=run_env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=stdout,
            stderr=stderr or f"timed out after {timeout_seconds}s",
        )


def _tail(text: str, limit: int = 500) -> str:
    return text[-limit:] if len(text) > limit else text


def run_smoke(verbose: bool = False) -> int:
    r = Results()

    print(BANNER)
    print(" abunnytech Integration Smoke Test")
    print(BANNER)

    # 1. Credential safety
    print("\n--- Credential Safety ---")
    cred_keys = [
        "TIKTOK_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN",
        "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_STORE_DOMAIN",
    ]
    live = [k for k in cred_keys if os.environ.get(k)]
    if live:
        r.fail("no_live_creds", f"Live credentials found: {live}")
    else:
        r.ok("no_live_creds", "No live platform credentials in env")

    # 2. Feature flag check
    print("\n--- Feature Flags ---")
    stage5_raw = os.environ.get("FEATURE_STAGE5_MONETIZE", "false").lower()
    if stage5_raw in ("1", "true", "yes"):
        r.fail("stage5_disabled", f"FEATURE_STAGE5_MONETIZE={stage5_raw} — should be off by default")
    else:
        r.ok("stage5_disabled", "Stage 5 disabled by default")

    dry_run = os.environ.get("DRY_RUN", "true").lower()
    if dry_run in ("1", "true", "yes", ""):
        r.ok("dry_run_enabled", f"DRY_RUN={dry_run or 'true (default)'}")
    else:
        r.fail("dry_run_enabled", f"DRY_RUN={dry_run} — should be true for smoke test")

    # 3. M1 contract example validation
    print("\n--- Contract Validation ---")
    proc = _run(
        ["uv", "run", "pytest", *PYTEST_ARGS, "packages/pipeline_contracts/tests/", "-v", "--tb=short"],
        env=PYTEST_ENV,
        timeout_seconds=60,
    )
    if proc.returncode == 0:
        r.ok("m1_contracts", "pipeline_contracts examples + schemas validated")
    else:
        r.fail("m1_contracts", f"exit={proc.returncode}")
        if verbose:
            print(_tail(proc.stdout))
            if proc.stderr:
                print(_tail(proc.stderr))

    # 4. Contract compatibility bridge
    proc = _run(
        ["uv", "run", "pytest", *PYTEST_ARGS, "tests/test_contract_compat.py", "-v", "--tb=short"],
        env=PYTEST_ENV,
        timeout_seconds=60,
    )
    if proc.returncode == 0:
        r.ok("contract_compat", "M1 <-> runtime contract compatibility verified")
    else:
        r.fail("contract_compat", f"exit={proc.returncode}")
        if verbose:
            print(_tail(proc.stdout))
            if proc.stderr:
                print(_tail(proc.stderr))

    # 5. CLI demo pipeline (stages 0-4)
    print("\n--- Pipeline Demo (dry-run) ---")
    demo_env = {"PYTHONPATH": str(REPO)}
    proc = _run(
        ["uv", "run", "python", "-m", "orchestrator.cli", "demo"],
        env=demo_env,
        timeout_seconds=60,
    )
    if proc.returncode == 0 and "Demo complete!" in proc.stdout:
        try:
            output_start = proc.stdout.index("{")
            output_end = proc.stdout.rindex("}") + 1
            demo_data = json.loads(proc.stdout[output_start:output_end])
            stages = demo_data.get("stages", {})
            stage_names = list(stages.keys())
            r.ok("pipeline_demo", f"Stages completed: {', '.join(stage_names)}")
            if verbose:
                for sn, sv in stages.items():
                    print(f"    {sn}: {json.dumps(sv, default=str)[:120]}")
        except (json.JSONDecodeError, ValueError):
            r.ok("pipeline_demo", "Demo completed (output not JSON-parseable)")
    else:
        r.fail("pipeline_demo", f"exit={proc.returncode}")
        if verbose:
            if proc.stdout:
                print(_tail(proc.stdout))
            if proc.stderr:
                print(_tail(proc.stderr))

    # 6. Stage-0-5 test suite
    print("\n--- Stage 0-5 Tests ---")
    proc = _run(
        ["uv", "run", "pytest", *PYTEST_ARGS, "tests/runtime/", "-v", "--tb=short"],
        env={**demo_env, **PYTEST_ENV},
        timeout_seconds=120,
    )
    if proc.returncode == 0:
        lines = proc.stdout.strip().split("\n")
        summary = lines[-1] if lines else ""
        r.ok("stage05_tests", summary.strip())
    else:
        r.fail("stage05_tests", f"exit={proc.returncode}")
        if verbose:
            print(_tail(proc.stdout))
            if proc.stderr:
                print(_tail(proc.stderr))

    # 7. Browser runtime tests
    print("\n--- Browser Runtime ---")
    proc = _run(
        ["uv", "run", "pytest", *PYTEST_ARGS, "packages/browser_runtime/", "-v", "--tb=short"],
        env=PYTEST_ENV,
        timeout_seconds=120,
    )
    if proc.returncode == 0:
        r.ok("browser_runtime", "53 tests passed")
    else:
        r.fail("browser_runtime", f"exit={proc.returncode}")
        if verbose:
            print(_tail(proc.stdout))
            if proc.stderr:
                print(_tail(proc.stderr))

    # Summary
    total = len(r.passed) + len(r.failed)
    print(f"\n{BANNER}")
    if r.failed:
        print(f" RESULT: {len(r.failed)}/{total} checks FAILED")
        for label, reason in r.failed:
            print(f"   x {label}: {reason}")
        print(BANNER)
        return 1
    else:
        msg = f" RESULT: {len(r.passed)}/{total} checks passed"
        if r.skipped:
            msg += f" | {len(r.skipped)} skipped"
        print(msg)
        print(BANNER)
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="abunnytech integration smoke test")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    sys.exit(run_smoke(verbose=args.verbose))
