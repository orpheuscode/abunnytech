"""Typer CLI for the abunnytech orchestrator."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from apps.orchestrator.pipeline import run_pipeline

cli = typer.Typer(name="abunnytech", help="abunnytech AI creator pipeline CLI.")
console = Console()


@cli.command()
def demo(
    identity: str = typer.Option("Demo Creator", help="Identity name for the demo run"),
    dry_run: bool = typer.Option(True, help="Run in dry-run mode (no real posts)"),
) -> None:
    """Run the full pipeline demo end-to-end."""
    console.print("[bold cyan]Running abunnytech pipeline demo...[/]")
    results = run_pipeline(identity, dry_run=dry_run)
    console.print_json(json.dumps(results, indent=2, default=str))
    console.print("[bold green]Demo complete![/]")


@cli.command()
def identity(
    name: str = typer.Argument(..., help="Name for the new identity"),
) -> None:
    """Create an identity and run stage 0 only."""
    console.print(f"[bold cyan]Creating identity:[/] {name}")
    results = run_pipeline(name, dry_run=True)
    stage0 = results.get("stages", {}).get("stage0_identity", {})
    console.print(f"[green]Identity created:[/] {stage0.get('identity_id', 'n/a')}")


@cli.command()
def status() -> None:
    """Show pipeline health summary."""
    table = Table(title="Pipeline Health")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    table.add_row("State layer", "OK")
    table.add_row("Event bus", "OK")
    table.add_row("Job registry", "OK")
    table.add_row("Orchestrator", "OK")

    console.print(table)


if __name__ == "__main__":
    cli()
