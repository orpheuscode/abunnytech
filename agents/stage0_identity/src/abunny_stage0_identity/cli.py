from __future__ import annotations

import argparse
from pathlib import Path

from abunny_stage0_identity.loader import load_persona_setup
from abunny_stage0_identity.pipeline import compile_stage0, write_stage0_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 0 — compile persona YAML/JSON into identity artifacts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    compile_p = sub.add_parser("compile", help="Compile persona setup to output directory")
    compile_p.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to persona .yaml, .yml, or .json",
    )
    compile_p.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Output directory for manifests and system_prompt.md",
    )
    compile_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Use stub integrations (no live API keys required)",
    )
    compile_p.add_argument(
        "--matrix-id",
        type=str,
        default=None,
        help="Optional fixed matrix_id (default: generated im_<hex>)",
    )

    args = parser.parse_args()
    if args.cmd == "compile":
        setup = load_persona_setup(args.input)
        result = compile_stage0(setup, dry_run=args.dry_run, matrix_id=args.matrix_id)
        write_stage0_artifacts(result, args.out)


if __name__ == "__main__":
    main()
