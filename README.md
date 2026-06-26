# Wind Turbine Lead Discovery Engine — Python Backend

AI-powered lead discovery and qualification system for KW20 and KW30 distributed wind turbines.
Covers North America, South America, and Africa.

## Setup

```bash
pip install anthropic python-dotenv pydantic
```

Create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# Full pipeline: discover → score → export
python main.py

# Specific region only
python main.py --region "South America"
python main.py --region "Africa"
python main.py --region "North America"

# Specific category only
python main.py --category "Mining"

# Limit number of leads generated
python main.py --leads 10

# Output format (default: both)
python main.py --output json
python main.py --output csv
python main.py --output both

# Hot leads only (score >= 85)
python main.py --hot-only
```

## Project Structure

```
wind_lead_engine/
├── main.py                  # Entry point and CLI
├── config.py                # Constants, scoring weights, categories
├── agents/
│   ├── discovery_agent.py   # Finds raw leads via Claude
│   ├── enrichment_agent.py  # Enriches leads with signals + decision makers
│   ├── scoring_agent.py     # Scores each lead 0–100
│   └── qualification_agent.py # Generates fit rationale + outreach angle
├── data/
│   └── lead_store.py        # In-memory lead store + deduplication
├── exporters/
│   ├── json_exporter.py     # Exports structured JSON
│   └── csv_exporter.py      # Exports CSV-ready format
└── utils/
    ├── models.py            # Pydantic data models
    ├── claude_client.py     # Shared Anthropic API client wrapper
    └── logger.py            # Console logging helpers
```
