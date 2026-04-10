"""
Pydantic models mirroring the official A2A protocol schema.

Spec reference: https://a2a-protocol.org/latest/specification/
Schema source: https://agent2agent.info/specification/core/

These models serve dual purpose:
  1. Strict structural validation of incoming Agent Cards.
  2. Typed input to the scoring engine (Phase 2).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class AgentProvider(BaseModel):
    """The organisation / entity that operates the agent."""

    organization: str = Field(..., description="Human-readable organisation name.")
    url: AnyHttpUrl = Field(..., description="Organisation's web presence.")


class AgentCapabilities(BaseModel):
    """Optional capabilities the agent declares support for."""

    streaming: bool = Field(
        default=False,
        description="Agent supports Server-Sent Events (SSE) streaming.",
    )
    pushNotifications: bool = Field(
        default=False,
        description="Agent can proactively push task-state notifications.",
    )
    stateTransitionHistory: bool = Field(
        default=False,
        description="Agent exposes task state-change history.",
    )


class SecurityScheme(BaseModel):
    """
    A single security scheme definition (mirrors OpenAPI SecurityScheme).
    Kept permissive via model_config so spec variants (Bearer, Basic,
    OAuth2, ApiKey, public) don't require separate subclasses in v1.
    """

    type: str = Field(..., description="Scheme type, e.g. 'http', 'apiKey', 'public'.")
    description: str | None = Field(default=None)

    model_config = {"extra": "allow"}


class AgentInterface(BaseModel):
    """
    A specific transport+protocol binding the agent supports.
    Allows agents to declare the same capability over multiple protocols.
    """

    url: AnyHttpUrl = Field(..., description="Endpoint URL for this interface.")
    transport: str = Field(
        ...,
        description="Transport identifier, e.g. 'JSONRPC', 'gRPC', 'REST'.",
    )
    protocolVersion: str | None = Field(
        default=None,
        description="A2A protocol version this interface implements.",
    )


class AgentSkill(BaseModel):
    """
    A distinct capability or function the agent can perform.

    Required: id, name, description, tags
    Strongly recommended for discoverability: examples, inputModes, outputModes
    """

    id: str = Field(
        ...,
        min_length=1,
        description="Unique, machine-readable identifier for the skill.",
    )
    name: str = Field(..., min_length=1, description="Human-readable skill name.")
    description: str = Field(
        ...,
        min_length=1,
        description="What this skill does. Quality here is key for discoverability.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable keywords that describe this skill.",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Example utterances / prompts that trigger this skill.",
    )
    inputModes: list[str] = Field(
        default_factory=list,
        description="MIME types accepted as input (e.g. 'text/plain', 'application/json').",
    )
    outputModes: list[str] = Field(
        default_factory=list,
        description="MIME types produced as output.",
    )

    @field_validator("tags", "examples", mode="before")
    @classmethod
    def _coerce_to_list(cls, v: Any) -> list:
        """Tolerate a bare string where a list is expected."""
        if isinstance(v, str):
            return [v]
        return v or []


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class AgentCard(BaseModel):
    """
    A self-describing manifest for an A2A agent.

    Required fields (per spec): name, url, version, capabilities, skills
    Everything else is optional but scored for discoverability quality.
    """

    # ── Required ──────────────────────────────────────────────────────────
    name: str = Field(..., min_length=1, description="Human-readable agent name.")
    url: AnyHttpUrl = Field(
        ..., description="Base URL where the A2A service is hosted."
    )
    version: str = Field(
        ...,
        description="Agent version string. SemVer (MAJOR.MINOR.PATCH) recommended.",
    )
    capabilities: AgentCapabilities = Field(
        ..., description="Declared A2A capability flags."
    )
    skills: list[AgentSkill] = Field(
        ...,
        min_length=1,
        description="At least one skill must be declared.",
    )

    # ── Optional but scored ───────────────────────────────────────────────
    description: str | None = Field(
        default=None,
        description="What this agent does. High-quality text dramatically boosts score.",
    )
    provider: AgentProvider | None = Field(
        default=None,
        description="Organisation operating this agent.",
    )
    documentationUrl: AnyHttpUrl | None = Field(
        default=None,
        description="URL to human-readable documentation.",
    )
    iconUrl: AnyHttpUrl | None = Field(
        default=None, description="URL to an image representing the agent."
    )
    protocolVersion: str | None = Field(
        default=None,
        description="A2A protocol version this card targets.",
    )

    # ── I/O Modes ─────────────────────────────────────────────────────────
    defaultInputModes: list[str] = Field(
        default_factory=lambda: ["text/plain"],
        description="Default MIME types accepted as input.",
    )
    defaultOutputModes: list[str] = Field(
        default_factory=lambda: ["text/plain"],
        description="Default MIME types produced as output.",
    )

    # ── Auth & Security ───────────────────────────────────────────────────
    securitySchemes: dict[str, SecurityScheme] | None = Field(
        default=None,
        description="Named security scheme definitions (mirrors OpenAPI).",
    )
    security: list[dict[str, list[str]]] | None = Field(
        default=None,
        description="Security requirements referencing securitySchemes.",
    )
    supportsAuthenticatedExtendedCard: bool = Field(
        default=False,
        description="If true, additional metadata is available post-auth.",
    )

    # ── Multi-interface ───────────────────────────────────────────────────
    additionalInterfaces: list[AgentInterface] | None = Field(
        default=None,
        description="Alternative transport/protocol bindings.",
    )

    # ── Extensions (forward-compat) ───────────────────────────────────────
    extensions: list[dict[str, Any]] | None = Field(
        default=None,
        description="Protocol extensions declared by this agent.",
    )

    model_config = {"extra": "allow"}  # tolerate unknown future fields

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("version")
    @classmethod
    def _accept_any_version(cls, v: str) -> str:
        """
        Does not reject non-SemVer strings (the spec doesn't mandate it).
        The Completeness scorer checks is_semver separately.
        """
        return v

    @model_validator(mode="after")
    def _check_skill_id_uniqueness(self) -> "AgentCard":
        ids = [s.id for s in self.skills]
        if len(ids) != len(set(ids)):
            duplicates = {i for i in ids if ids.count(i) > 1}
            raise ValueError(
                f"AgentCard contains duplicate skill IDs: {duplicates}. "
                "Each skill must have a unique 'id'."
            )
        return self

    # ── Convenience helpers (used by scoring engine) ──────────────────────

    @property
    def is_semver(self) -> bool:
        """True if version follows MAJOR.MINOR.PATCH[-prerelease][+build]."""
        semver_re = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        return bool(re.match(semver_re, self.version))

    @property
    def has_streaming(self) -> bool:
        return self.capabilities.streaming

    @property
    def has_push_notifications(self) -> bool:
        return self.capabilities.pushNotifications

    @property
    def has_multiple_interfaces(self) -> bool:
        return bool(self.additionalInterfaces and len(self.additionalInterfaces) >= 1)

    @property
    def all_tags(self) -> list[str]:
        """Flattened list of every tag across the card and all skills."""
        card_tags: list[str] = []
        for skill in self.skills:
            card_tags.extend(skill.tags)
        return card_tags
