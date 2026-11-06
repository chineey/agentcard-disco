import json
from agentcard_disco.parser import load
from agentcard_disco.models import AgentCard
import re

card = load("./tests/fixtures/good_card.json")

# replicate _resolved_url logic
def _resolved_url(c: AgentCard) -> str:
    if c.url:
        return str(c.url)
    if c.documentationUrl is not None:
        return str(c.documentationUrl)
    if c.provider is not None and c.provider.url:
        return str(c.provider.url)
    name_slug = re.sub(r"[^a-z0-9]+", "-", (c.name or "agent").strip().lower())
    name_slug = name_slug.strip("-") or "agent"
    return f"https://example.invalid/{name_slug}"

provider = card.provider
caps = card.capabilities
card_dict = {
    "name": card.name,
    "url": _resolved_url(card),
    "version": card.version if card.version is not None else "0.0.0",
    "capabilities": {
        "streaming": bool(getattr(caps, "streaming", False)),
        "pushNotifications": bool(getattr(caps, "pushNotifications", False)),
        "stateTransitionHistory": bool(getattr(caps, "stateTransitionHistory", False)),
    } if caps is not None else {},
    "description": card.description,
    "provider": {
        "organization": provider.organization,
        "url": str(provider.url),
    } if provider is not None else None,
    "documentationUrl": str(card.documentationUrl) if card.documentationUrl is not None else None,
    "iconUrl": str(card.iconUrl) if card.iconUrl is not None else None,
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
