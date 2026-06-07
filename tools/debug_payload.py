import json
from agentcard_disco.parser import load
from agentcard_disco.models import AgentCard
import re

card = load("./tests/fixtures/good_card.json")

# replicate _resolved_url logic
def _resolved_url(c: AgentCard) -> str:
    if getattr(c, "url", None):
        return str(c.url)
    if getattr(c, "documentationUrl", None):
        return str(c.documentationUrl)
    if getattr(c, "provider", None) and getattr(c.provider, "url", None):
        return str(c.provider.url)
    name_slug = re.sub(r"[^a-z0-9]+", "-", (c.name or "agent").strip().lower())
    name_slug = name_slug.strip("-") or "agent"
    return f"https://example.invalid/{name_slug}"

card_dict = {
    "name": card.name,
    "url": _resolved_url(card),
    "version": card.version if getattr(card, "version", None) is not None else "0.0.0",
    "capabilities": {
        "streaming": bool(getattr(card.capabilities, "streaming", False)),
        "pushNotifications": bool(getattr(card.capabilities, "pushNotifications", False)),
        "stateTransitionHistory": bool(getattr(card.capabilities, "stateTransitionHistory", False)),
    } if getattr(card, "capabilities", None) is not None else {},
    "description": card.description,
    "provider": {
        "organization": card.provider.organization,
        "url": str(card.provider.url),
    } if getattr(card, "provider", None) is not None else None,
    "documentationUrl": str(card.documentationUrl) if getattr(card, "documentationUrl", None) is not None else None,
    "iconUrl": str(card.iconUrl) if getattr(card, "iconUrl", None) is not None else None,
    "protocolVersion": card.protocolVersion,
    "skills": [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "tags": s.tags,
            "examples": s.examples,
            "inputModes": s.inputModes,
            "outputModes": s.outputModes,
        }
        for s in card.skills
    ],
}

print(json.dumps(card_dict, indent=2, ensure_ascii=False))
