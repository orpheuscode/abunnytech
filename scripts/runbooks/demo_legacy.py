"""End-to-end demo runbook.

Runs the full pipeline in-memory and prints results for each stage.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from orchestrator.pipeline import run_pipeline

console = Console()


def main() -> None:
    console.print("[bold cyan]abunnytech full demo runbook[/]\n")

    results = run_pipeline("TechBunny", dry_run=True)

    table = Table(title="Pipeline Results")
    table.add_column("Stage", style="cyan", min_width=20)
    table.add_column("Key", style="white")
    table.add_column("Value", style="green")

    stages = results.get("stages", {})
    for stage_name, stage_data in stages.items():
        if isinstance(stage_data, dict):
            for k, v in stage_data.items():
                table.add_row(stage_name, k, str(v))
        else:
            table.add_row(stage_name, "-", str(stage_data))

    console.print(table)
    console.print(f"\n[bold]Dry run:[/] {results.get('dry_run', True)}")
    console.print("[bold green]Demo runbook complete.[/]")


if __name__ == "__main__":
    main()
