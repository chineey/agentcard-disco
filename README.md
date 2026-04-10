# agentcard-disco

**Score and optimise [A2A](https://agent2agent.info/) Agent Cards for discoverability.**

`agentcard-disco` analyses an Agent Card JSON file and gives it a discoverability score across four heuristic dimensions (plus optional AI-assisted analysis), surfacing exactly what to fix before publishing to an A2A registry.

```
┌─────────────────────────────────────────────────────────────┐
│  agentcard-disco          discoverability score             │
│                                                             │
│  🏆  DataPulse Analytics Agent                              │
│    Source: tests/fixtures/good_card.json                    │
│                                                             │
│    Score: 88.0 / 100   (88%)   Grade:  A                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation

```bash
pip install agentcard-disco
```

For AI-assisted scoring (`--deep`):

```bash
pip install "agentcard-disco[deep]"
```

---

## Quick start

```bash
# Score a local card
agentcard-disco score ./agent-card.json

# Score from a URL
agentcard-disco score https://api.example.com/.well-known/agent-card.json

# + AI quality analysis (requires GEMINI_API_KEY in .env)
agentcard-disco score ./agent-card.json --deep

# Export report as JSON or Markdown
agentcard-disco score ./agent-card.json --format json --output report.json
agentcard-disco score ./agent-card.json --format markdown --output report.md

# CI gate — exit 1 if score is below 70%
agentcard-disco score ./agent-card.json --fail-under 70

# Get improvement suggestions only
agentcard-disco suggest ./agent-card.json --priority high

# Compare two cards side-by-side
agentcard-disco compare ./v1.json ./v2.json
```

---

## Scoring dimensions

| Dimension | Points | What it measures |
|-----------|-------:|-----------------|
| Metadata Richness | 0–30 | Description length, tags, examples, provider info |
| Semantic Specificity | 0–30 | Filler-word ratio, skill distinctness, action-verb density |
| Search Alignment | 0–20 | Tag and keyword coverage vs A2A registry query vocabulary |
| Completeness | 0–20 | SemVer, capabilities, auth declaration, protocol version |
| AI Quality *(--deep)* | 0–20 | Categorical quality judgments via Gemini |

**Grade scale:**

| Grade | Score |
|-------|-------|
| A | 85–100% |
| B | 70–84% |
| C | 50–69% |
| D | 30–49% |
| F | 0–29% |

---

## AI scoring setup (`--deep`)

1. Install the deep extra: `pip install "agentcard-disco[deep]"`
2. Get a free Gemini API key at https://aistudio.google.com/app/apikey
3. Add it to a `.env` file in your working directory:

```env
GEMINI_API_KEY="AIza..."
```

4. Run with `--deep`:

```bash
agentcard-disco score ./agent-card.json --deep
```

---

## Python API

```python
from agentcard_disco.parser import load
from agentcard_disco.scoring.engine import score

card = load("agent-card.json")        # also accepts http(s):// URLs
report = score(card)                  # Tier 1 only
report = score(card, deep=True)       # + AI analysis

print(report.grade.value)            # "A", "B", ...
print(report.percentage)             # 88.0
print(report.total_score)            # 88.0

for suggestion in report.all_suggestions:
    print(suggestion.priority, suggestion.field, suggestion.message)
```

---

## Commands

### `score`

```
agentcard-disco score SOURCE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--deep` | off | Enable Tier 2 AI analysis (+20 pts) |
| `--format` | terminal | `terminal`, `json`, or `markdown` |
| `--output FILE` | stdout | Write output to file |
| `--fail-under SCORE` | — | Exit 1 if percentage < SCORE |
| `--no-suggestions` | off | Hide suggestions table |
| `--no-detail` | off | Hide per-dimension details |

### `suggest`

```
agentcard-disco suggest SOURCE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--priority` | all | Filter: `all`, `high`, `medium`, `low` |
| `--format` | terminal | `terminal` or `json` |
| `--limit N` | 20 | Max suggestions to show |
| `--deep` | off | Include AI suggestions |

### `compare`

```
agentcard-disco compare SOURCE SOURCE [SOURCE ...] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | terminal | `terminal` or `json` |

---

## Development

```bash
git clone https://github.com/chinemeze/agentcard-disco
cd agentcard-disco
pip install -e ".[deep]"
pip install pytest pytest-cov mypy ruff

# Run tests
pytest tests/ -v

# Lint
ruff check src/

# Type check
mypy src/
```

---

## License

MIT
