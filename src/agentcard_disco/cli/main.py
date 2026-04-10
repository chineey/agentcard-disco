"""
agentcard-disco CLI

Entry point: `agentcard-disco` (defined in pyproject.toml)

Commands:
  score    — Score a single Agent Card and print the full report
  suggest  — Print only improvement suggestions (pipe-friendly)
  compare  — Compare two or more Agent Cards side-by-side

Examples:
  agentcard-disco score ./agent-card.json
  agentcard-disco score https://api.example.com/.well-known/agent-card.json
  agentcard-disco score ./card.json --format json --output report.json
  agentcard-disco score ./card.json --format markdown --output report.md
  agentcard-disco suggest ./card.json
  agentcard-disco suggest ./card.json --priority high
  agentcard-disco compare ./card-a.json ./card-b.json
"""

from __future__ import annotations

import sys

import click
from rich.console import Console

from agentcard_disco import __version__
from agentcard_disco.parser import FetchError, ParseError, load
from agentcard_disco.reporting.exporters import to_json, to_markdown, write_json, write_markdown
from agentcard_disco.reporting.terminal import render_compare, render_report
from agentcard_disco.scoring.engine import score as run_score
from agentcard_disco.scoring.result import Grade

_console = Console()
_err_console = Console(stderr=True)


# ── Shared utilities ───────────────────────────────────────────────────────

def _load_or_exit(source: str):
    """Load an AgentCard from source, printing a friendly error and exiting on failure."""
    try:
        return load(source)
    except ParseError as e:
        _err_console.print(f"[bold red]Parse error:[/bold red] {e}")
        sys.exit(1)
    except FetchError as e:
        _err_console.print(f"[bold red]Fetch error:[/bold red] {e}")
        sys.exit(1)


# ── CLI group ──────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name="agentcard-disco")
def cli():
    """
    \b
    agentcard-disco — Score and optimise A2A Agent Cards for discoverability.

    Tier 1 (always on):
      • Metadata Richness    (0-30 pts)
      • Semantic Specificity (0-30 pts)
      • Search Alignment     (0-20 pts)
      • Completeness         (0-20 pts)

    Tier 2 (add --deep, requires ANTHROPIC_API_KEY in .env):
      • AI Quality           (0-20 pts)

    Tier 1 total: 100 pts.  With --deep: up to 120 pts.  Graded A–F.
    """


# ── score command ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("source", metavar="SOURCE")
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["terminal", "json", "markdown"], case_sensitive=False),
    default="terminal",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output", "-o",
    "output_path",
    default=None,
    metavar="FILE",
    help="Write output to FILE instead of stdout. Required for non-terminal formats in CI.",
)
@click.option(
    "--no-suggestions",
    is_flag=True,
    default=False,
    help="Omit the suggestions table from terminal output.",
)
@click.option(
    "--no-detail",
    is_flag=True,
    default=False,
    help="Omit per-dimension check/fail details from terminal output.",
)
@click.option(
    "--fail-under",
    "fail_under",
    type=click.IntRange(0, 100),
    default=None,
    metavar="SCORE",
    help="Exit with code 1 if the overall percentage is below SCORE. Useful in CI.",
)
@click.option(
    "--deep",
    "deep",
    is_flag=True,
    default=False,
    help=(
        "Enable Tier 2 AI quality analysis (+20 pts). "
        "Requires GEMINI_API_KEY in .env and: pip install agentcard-disco[deep]"
    ),
)
def score(
    source: str,
    output_format: str,
    output_path: str | None,
    no_suggestions: bool,
    no_detail: bool,
    fail_under: int | None,
    deep: bool,
):
    """
    Score a single Agent Card and print a discoverability report.

    SOURCE can be a local .json file path or an http(s):// URL.

    \b
    Examples:
      agentcard-disco score ./agent-card.json
      agentcard-disco score ./card.json --deep               # + AI quality analysis
      agentcard-disco score ./card.json --format json --output report.json
      agentcard-disco score ./card.json --format markdown -o report.md
      agentcard-disco score ./card.json --fail-under 70      # non-zero exit if grade < B
    """
    if deep:
        _console.print("[dim]🤖  Running Tier 2 AI quality analysis…[/dim]")
    card = _load_or_exit(source)
    report = run_score(card, source=source, deep=deep)

    if output_format == "terminal":
        render_report(
            report,
            show_checks=not no_detail,
            show_suggestions=not no_suggestions,
        )
        if output_path:
            # Also write markdown when --output is given with terminal format
            write_markdown(report, output_path)
            _console.print(f"[dim]Markdown report written to {output_path}[/dim]")

    elif output_format == "json":
        content = to_json(report)
        if output_path:
            write_json(report, output_path)
            _console.print(f"[dim]JSON report written to {output_path}[/dim]")
        else:
            click.echo(content)

    elif output_format == "markdown":
        content = to_markdown(report)
        if output_path:
            write_markdown(report, output_path)
            _console.print(f"[dim]Markdown report written to {output_path}[/dim]")
        else:
            click.echo(content)

    # CI exit code
    if fail_under is not None and report.percentage < fail_under:
        _err_console.print(
            f"[bold red]FAIL:[/bold red] Score {report.percentage:.0f}% is below "
            f"threshold {fail_under}%"
        )
        sys.exit(1)


# ── suggest command ────────────────────────────────────────────────────────

@cli.command()
@click.argument("source", metavar="SOURCE")
@click.option(
    "--priority", "-p",
    type=click.Choice(["all", "high", "medium", "low"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Filter suggestions by priority level.",
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["terminal", "json"], case_sensitive=False),
    default="terminal",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--limit", "-n",
    type=int,
    default=20,
    show_default=True,
    help="Maximum number of suggestions to display.",
)
@click.option(
    "--deep",
    "deep",
    is_flag=True,
    default=False,
    help="Enable Tier 2 AI quality analysis to surface richer suggestions.",
)
def suggest(
    source: str,
    priority: str,
    output_format: str,
    limit: int,
    deep: bool,
):
    """
    Print improvement suggestions for an Agent Card.

    SOURCE can be a local .json file path or an http(s):// URL.
    Suggestions are sorted by priority (high → medium → low).

    \b
    Examples:
      agentcard-disco suggest ./card.json
      agentcard-disco suggest ./card.json --deep             # + AI suggestions
      agentcard-disco suggest ./card.json --priority high
      agentcard-disco suggest ./card.json --format json
    """
    if deep:
        _console.print("[dim]🤖  Running Tier 2 AI quality analysis…[/dim]")
    card = _load_or_exit(source)
    report = run_score(card, source=source, deep=deep)
    suggestions = report.all_suggestions

    # Filter
    priority_map = {"high": 1, "medium": 2, "low": 3}
    if priority != "all":
        target = priority_map[priority]
        suggestions = [s for s in suggestions if s.priority == target]

    suggestions = suggestions[:limit]

    if output_format == "json":
        import json as _json
        data = [
            {
                "priority": s.priority,
                "dimension": s.dimension,
                "field": s.field,
                "message": s.message,
            }
            for s in suggestions
        ]
        click.echo(_json.dumps(data, indent=2))
        return

    # Terminal output
    _console.print()
    _console.print(
        f"[bold]{report.card_name}[/bold]  "
        f"[dim]{report.total_score:.0f}/{report.max_total:.0f} pts  "
        f"Grade {report.grade.value}[/dim]"
    )
    _console.print()

    if not suggestions:
        _console.print("[green]No suggestions at this priority level — great work![/green]")
        return

    priority_icons = {1: "[bold red]●[/bold red]", 2: "[yellow]●[/yellow]", 3: "[dim]●[/dim]"}
    priority_labels = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}

    for i, s in enumerate(suggestions, 1):
        _console.print(
            f"  {priority_icons[s.priority]} [bold]{priority_labels[s.priority]}[/bold]  "
            f"[dim]{s.dimension}[/dim]"
        )
        if s.field:
            _console.print(f"     [italic dim]Field:[/italic dim] [italic]{s.field}[/italic]")
        _console.print(f"     {s.message}")
        if i < len(suggestions):
            _console.print()

    _console.print()
    _console.print(
        f"[dim]{len(suggestions)} suggestion(s) shown "
        f"({'filtered to ' + priority if priority != 'all' else 'all priorities'})[/dim]"
    )
    _console.print()


# ── compare command ────────────────────────────────────────────────────────

@cli.command()
@click.argument("sources", nargs=-1, required=True, metavar="SOURCE...")
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["terminal", "json"], case_sensitive=False),
    default="terminal",
    show_default=True,
    help="Output format.",
)
def compare(sources: tuple[str, ...], output_format: str):
    """
    Compare two or more Agent Cards side-by-side.

    Pass two or more SOURCE paths or URLs to compare them.
    The winner in each dimension is highlighted.

    \b
    Examples:
      agentcard-disco compare ./card-a.json ./card-b.json
      agentcard-disco compare ./v1.json ./v2.json ./v3.json
      agentcard-disco compare ./card-a.json https://example.com/.well-known/agent-card.json
    """
    if len(sources) < 2:
        _err_console.print("[bold red]Error:[/bold red] compare requires at least 2 sources.")
        sys.exit(1)

    reports = []
    for src in sources:
        card = _load_or_exit(src)
        reports.append(run_score(card, source=src))

    if output_format == "json":
        import json as _json
        data = {
            "comparison": [
                {
                    "card": r.card_name,
                    "source": r.source,
                    "overall": {
                        "score": r.total_score,
                        "percentage": r.percentage,
                        "grade": r.grade.value,
                    },
                    "dimensions": {
                        d.name: {
                            "score": d.score,
                            "percentage": d.percentage,
                            "grade": d.grade.value,
                        }
                        for d in r.dimensions
                    },
                }
                for r in reports
            ]
        }
        click.echo(_json.dumps(data, indent=2))
        return

    render_compare(reports)

    # Print winner
    winner = max(reports, key=lambda r: r.total_score)
    _console.print(
        f"  [bold green]Winner:[/bold green] {winner.card_name}  "
        f"[dim]({winner.percentage:.0f}% — Grade {winner.grade.value})[/dim]"
    )
    _console.print()


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
