"""
Result types for the scoring engine.

All analyzers return a DimensionResult. The engine assembles them into a
ScoreReport which is the single object passed to reporters and CLI commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Grade(str, Enum):
    """Letter grade derived from total score (0-100)."""
    A = "A"   # 85-100  Excellent discoverability
    B = "B"   # 70-84   Good, minor improvements possible
    C = "C"   # 50-69   Fair, notable gaps
    D = "D"   # 30-49   Poor, significant issues
    F = "F"   #  0-29   Failing, major overhaul needed

    @classmethod
    def from_score(cls, score: float) -> "Grade":
        if score >= 85:
            return cls.A
        if score >= 70:
            return cls.B
        if score >= 50:
            return cls.C
        if score >= 30:
            return cls.D
        return cls.F

    @property
    def color(self) -> str:
        """Rich markup color for terminal output."""
        return {
            Grade.A: "bright_green",
            Grade.B: "green",
            Grade.C: "yellow",
            Grade.D: "red",
            Grade.F: "bright_red",
        }[self]

    @property
    def emoji(self) -> str:
        return {
            Grade.A: "🏆",
            Grade.B: "✅",
            Grade.C: "⚠️",
            Grade.D: "❌",
            Grade.F: "💀",
        }[self]


@dataclass
class Suggestion:
    """A single actionable improvement suggestion."""
    dimension: str          # Which analyzer raised it
    priority: int           # 1=high, 2=medium, 3=low
    message: str            # Human-readable description
    field: str | None = None  # The specific AgentCard field to fix

    def __lt__(self, other: "Suggestion") -> bool:
        return self.priority < other.priority


@dataclass
class DimensionResult:
    """Result from a single scoring dimension."""
    name: str               # e.g. "Metadata Richness"
    score: float            # Points earned
    max_score: float        # Maximum possible points
    checks: list[str]       # Descriptions of passing checks  ✓
    failures: list[str]     # Descriptions of failing checks  ✗
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        if self.max_score == 0:
            return 0.0
        return round((self.score / self.max_score) * 100, 1)

    @property
    def grade(self) -> Grade:
        return Grade.from_score(self.percentage)


@dataclass
class ScoreReport:
    """
    The complete scoring report for one AgentCard.
    Produced by the engine, consumed by reporters and CLI commands.
    """
    card_name: str
    source: str                         # File path or URL
    dimensions: list[DimensionResult]
    ai_enhanced: bool = False           # True when Tier 2 AI analysis ran (--deep)

    @property
    def total_score(self) -> float:
        return round(sum(d.score for d in self.dimensions), 2)

    @property
    def max_total(self) -> float:
        return sum(d.max_score for d in self.dimensions)

    @property
    def percentage(self) -> float:
        if self.max_total == 0:
            return 0.0
        return round((self.total_score / self.max_total) * 100, 1)

    @property
    def grade(self) -> Grade:
        return Grade.from_score(self.percentage)

    @property
    def all_suggestions(self) -> list[Suggestion]:
        """All suggestions, sorted by priority (high first)."""
        suggestions: list[Suggestion] = []
        for d in self.dimensions:
            suggestions.extend(d.suggestions)
        return sorted(suggestions)

    def dimension(self, name: str) -> DimensionResult | None:
        for d in self.dimensions:
            if d.name == name:
                return d
        return None
