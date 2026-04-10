# agentcard-disco — Usage Guide

Score and optimise A2A Agent Cards for discoverability.

---

## Installation

```bash
cd agentcard-disco

# Tier 1 only (no AI, no API key needed)
pip install -e .

# Tier 1 + Tier 2 AI scoring
pip install -e ".[deep]"
```

---

## Configuration

Copy the example below into `.env` at the project root.  
Only needed if you want `--deep` AI scoring.

```env
GEMINI_API_KEY="your-key-here"
```

Get a free key at: https://aistudio.google.com/app/apikey

---

## Commands

### `score` — full discoverability report

```bash
agentcard-disco score <source>
```

| Option | Description |
|--------|-------------|
| `--deep` | Enable Tier 2 AI analysis (+20 pts). Requires `GEMINI_API_KEY`. |
| `--format terminal\|json\|markdown` | Output format (default: terminal) |
| `--output FILE` | Write output to a file |
| `--fail-under SCORE` | Exit code 1 if score % is below this (useful in CI) |
| `--no-suggestions` | Hide the suggestions table |
| `--no-detail` | Hide per-dimension check/fail details |

**Examples:**

```bash
agentcard-disco score ./agent-card.json
agentcard-disco score ./agent-card.json --deep
agentcard-disco score ./agent-card.json --format json --output report.json
agentcard-disco score ./agent-card.json --format markdown --output report.md
agentcard-disco score ./agent-card.json --fail-under 70
```

---

### `suggest` — improvement suggestions only

```bash
agentcard-disco suggest <source>
```

| Option | Description |
|--------|-------------|
| `--priority all\|high\|medium\|low` | Filter by priority (default: all) |
| `--format terminal\|json` | Output format (default: terminal) |
| `--limit N` | Max number of suggestions to show (default: 20) |
| `--deep` | Include AI-powered suggestions |

**Examples:**

```bash
agentcard-disco suggest ./agent-card.json
agentcard-disco suggest ./agent-card.json --priority high
agentcard-disco suggest ./agent-card.json --format json
```

---

### `compare` — side-by-side comparison

```bash
agentcard-disco compare <source1> <source2> [source3 ...]
```

| Option | Description |
|--------|-------------|
| `--format terminal\|json` | Output format (default: terminal) |

**Examples:**

```bash
agentcard-disco compare ./card-a.json ./card-b.json
agentcard-disco compare ./v1.json ./v2.json ./v3.json
```

---

## Scoring

| Dimension | Points | Tier |
|-----------|-------:|------|
| Metadata Richness | 0–30 | 1 |
| Semantic Specificity | 0–30 | 1 |
| Search Alignment | 0–20 | 1 |
| Completeness | 0–20 | 1 |
| AI Quality (`--deep`) | 0–20 | 2 |

**Grade scale** (based on %):

| Grade | Range |
|-------|-------|
| A | 85–100% |
| B | 70–84% |
| C | 50–69% |
| D | 30–49% |
| F | 0–29% |

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Source can be a local file or a URL

```bash
agentcard-disco score ./local-card.json
agentcard-disco score https://api.example.com/.well-known/agent-card.json
```
