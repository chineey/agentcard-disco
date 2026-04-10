"""
Analyzer 4 — Completeness (0–20 points)

Evaluates whether the AgentCard is "production-ready" from a technical
integration standpoint. Focuses on fields that gate automated agent selection
and multi-agent pipeline compatibility.

Checks:
  1. SemVer version string             (0-4 pts)
  2. Capability declarations           (0-6 pts)  streaming, push, history
  3. Multiple interface declarations   (0-4 pts)
  4. Security / auth declaration       (0-4 pts)
  5. Protocol version declared         (0-2 pts)
"""

from __future__ import annotations

import re

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring.result import DimensionResult, Suggestion

# SemVer: MAJOR.MINOR.PATCH with optional pre-release and build metadata
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def analyze(card: AgentCard) -> DimensionResult:
    score = 0.0
    checks: list[str] = []
    failures: list[str] = []
    suggestions: list[Suggestion] = []

    # ── 1. SemVer version (0-4 pts) ───────────────────────────────────────
    if _SEMVER_RE.match(card.version):
        score += 4.0
        checks.append(f"Version follows SemVer: '{card.version}'")
    else:
        # Check if it's at least MAJOR.MINOR (partial credit)
        if re.match(r"^\d+\.\d+$", card.version):
            score += 2.0
            failures.append(
                f"Version '{card.version}' is MAJOR.MINOR — add a PATCH segment (e.g. '{card.version}.0')"
            )
            suggestions.append(Suggestion(
                dimension="Completeness",
                priority=2,
                message=(
                    f"Version '{card.version}' is missing the PATCH segment. "
                    "Use full SemVer (MAJOR.MINOR.PATCH) so clients can reliably compare versions."
                ),
                field="version",
            ))
        else:
            failures.append(
                f"Version '{card.version}' does not follow SemVer (expected MAJOR.MINOR.PATCH)"
            )
            suggestions.append(Suggestion(
                dimension="Completeness",
                priority=1,
                message=(
                    f"Change version from '{card.version}' to a SemVer string like '1.0.0'. "
                    "SemVer allows orchestrators and registries to filter by version ranges "
                    "and detect breaking changes."
                ),
                field="version",
            ))

    # ── 2. Capability declarations (0-6 pts) ──────────────────────────────
    cap = card.capabilities

    if cap.streaming:
        score += 3.0
        checks.append("Streaming (SSE) capability declared")
    else:
        failures.append("Streaming not declared — agents without streaming score lower in latency-sensitive pipelines")
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=2,
            message=(
                "If this agent supports streaming responses, set 'capabilities.streaming: true'. "
                "Streaming is increasingly required in agentic pipelines for real-time feedback."
            ),
            field="capabilities.streaming",
        ))

    if cap.pushNotifications:
        score += 2.0
        checks.append("Push notifications capability declared")
    else:
        failures.append("Push notifications not declared")
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=3,
            message=(
                "Consider implementing push notifications ('capabilities.pushNotifications: true'). "
                "This allows clients to receive async task updates via webhooks, "
                "enabling fire-and-forget integration patterns."
            ),
            field="capabilities.pushNotifications",
        ))

    if cap.stateTransitionHistory:
        score += 1.0
        checks.append("State transition history capability declared")

    # ── 3. Multiple interface declarations (0-4 pts) ──────────────────────
    if card.has_multiple_interfaces:
        ifaces = card.additionalInterfaces or []
        transports = {i.transport for i in ifaces}
        score += 4.0
        checks.append(
            f"Multiple interfaces declared ({len(ifaces) + 1} total), "
            f"transports: {', '.join(transports)}"
        )
    else:
        # Still check if the primary interface is at least HTTPS
        primary_url = str(card.url)
        if primary_url.startswith("https://"):
            score += 1.0
            checks.append("Primary interface uses HTTPS")
        else:
            failures.append("Primary interface is not HTTPS — production deployments should use TLS")
            suggestions.append(Suggestion(
                dimension="Completeness",
                priority=2,
                message=(
                    "The agent URL uses HTTP instead of HTTPS. "
                    "Production agents should always serve over TLS."
                ),
                field="url",
            ))

        failures.append("Only one transport interface declared")
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=2,
            message=(
                "Add alternative transport bindings via 'additionalInterfaces' "
                "(e.g. gRPC alongside JSON-RPC). "
                "Multi-interface agents are preferred by orchestrators that need "
                "high-throughput or low-latency communication."
            ),
            field="additionalInterfaces",
        ))

    # ── 4. Security / auth declaration (0-4 pts) ──────────────────────────
    has_security_schemes = bool(card.securitySchemes)
    has_security_requirements = bool(card.security)
    is_public = (
        card.securitySchemes is not None
        and any(
            v.type.lower() == "public"
            for v in card.securitySchemes.values()
        )
    )

    if has_security_schemes and has_security_requirements:
        score += 4.0
        scheme_names = list(card.securitySchemes.keys()) if card.securitySchemes else []
        checks.append(
            f"Security schemes declared and applied: {', '.join(scheme_names)}"
        )
    elif is_public:
        score += 3.0
        checks.append("Agent explicitly declares public (unauthenticated) access")
    elif has_security_schemes:
        score += 2.0
        failures.append(
            "Security schemes defined but 'security' requirements not applied"
        )
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=2,
            message=(
                "You've defined 'securitySchemes' but haven't applied them via the 'security' field. "
                "Add a 'security' array referencing your scheme(s) so clients know which to use."
            ),
            field="security",
        ))
    else:
        failures.append("No security scheme or authentication method declared")
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=1,
            message=(
                "Declare a 'securitySchemes' block. If the agent is publicly accessible, "
                "use type: 'public'. If it requires auth, declare the scheme "
                "(e.g. Bearer JWT, API key). Undeclared auth causes integration failures."
            ),
            field="securitySchemes",
        ))

    # ── 5. Protocol version (0-2 pts) ─────────────────────────────────────
    if card.protocolVersion:
        score += 2.0
        checks.append(f"A2A protocol version declared: '{card.protocolVersion}'")
    else:
        failures.append("No A2A 'protocolVersion' field — clients cannot verify compatibility")
        suggestions.append(Suggestion(
            dimension="Completeness",
            priority=3,
            message=(
                "Add 'protocolVersion' (e.g. '1.0.0') to the card. "
                "This allows clients and registries to filter for protocol-compatible agents "
                "and helps with forward/backward compatibility management."
            ),
            field="protocolVersion",
        ))

    return DimensionResult(
        name="Completeness",
        score=round(score, 2),
        max_score=20.0,
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )
