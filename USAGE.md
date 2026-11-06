# Usage

### `auth`
Save your API key for `--deep` scoring (one-time setup).
```bash
agentcard-disco auth acd_your_key_here
```

### `score`
Score a single Agent Card and print the discoverability report. Accepts local file paths or `http(s)://` URLs.
```bash
# Core scoring (Tier 1)
agentcard-disco score ./agent-card.json

# Scoring with Tier 2 AI quality analysis
agentcard-disco score ./agent-card.json --deep

# Export report to JSON or Markdown
agentcard-disco score ./agent-card.json --format json --output report.json
agentcard-disco score ./agent-card.json --format markdown --output report.md

# Fail CI pipeline if score falls under a threshold (e.g. 70%)
agentcard-disco score ./agent-card.json --fail-under 70
```

### `suggest`
Print only the prioritized improvement suggestions for the card.
```bash
# All suggestions
agentcard-disco suggest ./agent-card.json

# Filter suggestions by priority (high, medium, or low)
agentcard-disco suggest ./agent-card.json --priority high
```

### `compare`
Compare two or more Agent Cards side-by-side.
```bash
# Compare local and remote cards side-by-side
agentcard-disco compare ./card-a.json ./card-b.json
```
