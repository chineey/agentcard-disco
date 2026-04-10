"""
Terminal reporter — renders a ScoreReport to the terminal using `rich`.

Produces a structured, color-coded report with:
  - Agent name + source + overall grade banner
  - Per-dimension score bars with pass/fail checks
  - Prioritised improvement suggestions
  - A final summary footer
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from agentcard_disco.scoring.result import DimensionResult, Grade, ScoreReport, Suggestion

# Shared console — callers can pass their own for testing
_DEFAULT_CONSOLE = Console()


# ── Grade styling ──────────────────────────────────────────────────────────

_GRADE_STYLE: dict[Grade, str] = {
    Grade.A: "bold bright_green",
    Grade.B: "bold green",
    Grade.C: "bold yellow",
    Grade.D: "bold red",
    Grade.F: "bold bright_red",
}

_PRIORITY_STYLE = {1: "bold red", 2: "yellow", 3: "dim"}
_PRIORITY_LABEL = {1: "HIGH", 2: "MED ", 3: "LOW "}

_CHECK_ICON = "[green]✓[/green]"
_FAIL_ICON  = "[red]✗[/red]"


# ── Helpers ────────────────────────────────────────────────────────────────

def _grade_panel_text(report: ScoreReport) -> Text:
    grade = report.grade
    style = _GRADE_STYLE[grade]
    t = Text()
    t.append(f"{grade.emoji}  ", style="")
    t.append(f"{report.card_name}\n", style="bold")
    t.append(f"  Source: {report.source}\n", style="dim")
    t.append(f"\n  Score: {report.total_score:.1f} / {report.max_total:.0f}  ", style="")
    t.append(f"({report.percentage:.0f}%)", style="dim")
    t.append("   Grade: ", style="")
    t.append(f" {grade.value} ", style=f"reverse {style}")
    if report.ai_enhanced:
        t.append("   🤖 AI-enhanced", style="dim")
    return t


def _score_bar(score: float, max_score: float, width: int = 24) -> str:
    """ASCII progress bar for a single dimension."""
    ratio = score / max_score if max_score else 0
    filled = round(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = round(ratio * 100)
    return f"[{'green' if pct >= 70 else 'yellow' if pct >= 50 else 'red'}]{bar}[/] {pct:3d}%"


def _dimension_table(dimensions: list[DimensionResult]) -> Table:
    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold dim",
        show_edge=False,
        padding=(0, 1),
    )
    tbl.add_column("Dimension", style="bold", min_width=22)
    tbl.add_column("Score", justify="right", min_width=10)
    tbl.add_column("Progress", min_width=32)
    tbl.add_column("Grade", justify="center", min_width=5)

    for dim in dimensions:
        grade = dim.grade
        tbl.add_row(
            dim.name,
            f"{dim.score:.1f} / {dim.max_score:.0f}",
            _score_bar(dim.score, dim.max_score),
            Text(f" {grade.value} ", style=f"reverse {_GRADE_STYLE[grade]}"),
        )
    return tbl


def _checks_table(dim: DimensionResult) -> Table:
    tbl = Table(
        box=box.SIMPLE,
        show_header=False,
        show_edge=False,
        padding=(0, 1),
    )
    tbl.add_column("Icon", width=3)
    tbl.add_column("Detail")

    for c in dim.checks:
        tbl.add_row(_CHECK_ICON, Text(c, style="dim"))
    for f in dim.failures:
        tbl.add_row(_FAIL_ICON, Text(f, style=""))
    return tbl


def _suggestions_table(suggestions: list[Suggestion]) -> Table:
    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold dim",
        show_edge=False,
        padding=(0, 1),
    )
    tbl.add_column("Pri", width=5)
    tbl.add_column("Dimension", min_width=20)
    tbl.add_column("Field", style="dim italic", min_width=20)
    tbl.add_column("Suggestion")

    for s in suggestions:
        tbl.add_row(
            Text(_PRIORITY_LABEL[s.priority], style=_PRIORITY_STYLE[s.priority]),
            s.dimension,
            s.field or "—",
            s.message,
        )
    return tbl


# ── Public API ─────────────────────────────────────────────────────────────

def render_report(
    report: ScoreReport,
    *,
    console: Console | None = None,
    show_checks: bool = True,
    show_suggestions: bool = True,
    max_suggestions: int = 10,
) -> None:
    """
    Print a complete ScoreReport to the terminal.

    Args:
        report:           The ScoreReport to render.
        console:          Optional Rich Console (uses default if None).
        show_checks:      Whether to show per-dimension check/fail details.
        show_suggestions: Whether to render the suggestions table.
        max_suggestions:  Cap on number of suggestions shown.
    """
    con = console or _DEFAULT_CONSOLE

    # ── Banner ─────────────────────────────────────────────────────────────
    con.print()
    con.print(Panel(
        _grade_panel_text(report),
        title="[bold]agentcard-disco[/bold]",
        subtitle="[dim]discoverability score[/dim]",
        border_style=_GRADE_STYLE[report.grade].replace("bold ", ""),
        padding=(1, 3),
    ))

    # ── Dimension summary ──────────────────────────────────────────────────
    con.print()
    con.print(Rule("[bold]Dimension Scores[/bold]", style="dim"))
    con.print(_dimension_table(report.dimensions))

    # ── Per-dimension detail ───────────────────────────────────────────────
    if show_checks:
        con.print()
        con.print(Rule("[bold]Detail[/bold]", style="dim"))
        for dim in report.dimensions:
            con.print(f"\n  [bold]{dim.name}[/bold]  "
                      f"[dim]{dim.score:.1f}/{dim.max_score:.0f} pts[/dim]")
            con.print(_checks_table(dim))

    # ── Suggestions ────────────────────────────────────────────────────────
    if show_suggestions:
        all_suggestions = report.all_suggestions[:max_suggestions]
        if all_suggestions:
            con.print()
            con.print(Rule(f"[bold]Improvement Suggestions[/bold] "
                           f"[dim]({len(all_suggestions)} of {len(report.all_suggestions)})[/dim]",
                           style="dim"))
            con.print()
            con.print(_suggestions_table(all_suggestions))

    # ── Footer ─────────────────────────────────────────────────────────────
    con.print()
    con.print(Rule(style="dim"))
    high_count = sum(1 for s in report.all_suggestions if s.priority == 1)
    if high_count:
        con.print(
            f"  [red]▲ {high_count} high-priority issue(s) to fix before publishing.[/red]"
        )
    elif report.grade in (Grade.A, Grade.B):
        con.print(
            "  [green]✓ This card is ready to publish to an A2A registry.[/green]"
        )
    con.print()


def render_compare(
    reports: list[ScoreReport],
    *,
    console: Console | None = None,
) -> None:
    """
    Side-by-side comparison table for multiple ScoreReports.

    Args:
        reports: List of ScoreReport objects to compare.
        console: Optional Rich Console.
    """
    con = console or _DEFAULT_CONSOLE

    con.print()
    con.print(Rule("[bold]Agent Card Comparison[/bold]", style="dim"))
    con.print()

    tbl = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold dim",
        padding=(0, 1),
    )
    tbl.add_column("Dimension", style="bold", min_width=22)

    for r in reports:
        short_name = r.card_name[:18] + "…" if len(r.card_name) > 18 else r.card_name
        tbl.add_column(short_name, justify="center", min_width=14)

    # Overall row
    row: list[str | Text] = [Text("Overall", style="bold")]
    for r in reports:
        grade = r.grade
        row.append(
            Text(
                f"{r.percentage:.0f}%  {grade.value}",
                style=_GRADE_STYLE[grade],
            )
        )
    tbl.add_row(*row, end_section=True)

    # Per-dimension rows
    all_dim_names = [d.name for d in reports[0].dimensions]
    for dim_name in all_dim_names:
        row = [Text(dim_name)]
        for r in reports:
            dim = r.dimension(dim_name)
            if dim:
                pct = dim.percentage
                style = "green" if pct >= 70 else "yellow" if pct >= 50 else "red"
                row.append(Text(f"{dim.score:.0f}/{dim.max_score:.0f}  ({pct:.0f}%)", style=style))
            else:
                row.append(Text("—", style="dim"))
        tbl.add_row(*row)

    con.print(tbl)
    con.print()
