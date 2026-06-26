"""
Central configuration for the wind turbine lead discovery engine.

All prompts, scoring weights, category lists, product criteria, and
geographic scope are defined here so agents stay data-free.
"""

from __future__ import annotations

# ── geographic scope ──────────────────────────────────────────────────────────
REGIONS: list[str] = [
    "North America",   # USA, Canada, Mexico
    "South America",   # Brazil, Chile, Argentina, Colombia, Paraguay, etc.
    "Africa",          # South Africa, Nigeria, Kenya, Tanzania, Ghana, etc.
]

# ── buyer categories ──────────────────────────────────────────────────────────
BUYER_CATEGORIES: list[str] = [
    "Microgrid developers/operators",
    "Data centers",
    "Rural electric cooperatives",
    "Tribal nations / indigenous energy programs",
    "Agriculture (farms, irrigation, food processing)",
    "Hospitals / healthcare systems",
    "Universities / campuses",
    "Manufacturing / industrial facilities",
    "Airports / transportation hubs",
    "Military / government facilities",
    "Telecom / remote infrastructure",
    "Battery storage / renewable developers",
    "Water treatment / utilities",
    "Mining / oil & gas remote operations",
]

# Short labels used for filtering and display
CATEGORY_LABELS: list[str] = [
    "Microgrid",
    "Data Center",
    "Rural Electric",
    "Tribal",
    "Agriculture",
    "Hospital",
    "University",
    "Manufacturing",
    "Airport",
    "Military / Government",
    "Telecom",
    "Battery Storage / Renewable",
    "Water Treatment",
    "Mining / Oil & Gas",
]

# ── energy buyer signals ──────────────────────────────────────────────────────
ENERGY_SIGNALS: list[str] = [
    "Microgrid development or planning",
    "Backup generation investments",
    "Diesel generator replacement programs",
    "Solar + battery hybrid systems",
    "ESG / net-zero commitments",
    "Remote or off-grid operations",
    "High energy cost exposure",
    "Recent facility expansion",
    "DOE or government energy grants",
    "Infrastructure modernization projects",
    "Climate resilience planning",
    "Critical infrastructure status",
    "Rural electrification mandate",
    "Load-shedding resilience (Africa)",
    "Renewable project pipeline",
    "Interconnection queue filings",
]

# ── product criteria ──────────────────────────────────────────────────────────
PRODUCT_CRITERIA = {
    "KW20": {
        "name": "KW20 (~20 kW)",
        "best_for": [
            "farms and small agricultural facilities",
            "small commercial facilities",
            "pilot microgrids",
            "rural utilities and co-ops",
            "tribal pilot projects",
            "supplemental renewable systems",
            "remote telecom tower sites",
            "small community off-grid systems",
            "government ranger stations and remote outposts",
        ],
        "typical_load": "Small — single facility or site under ~50 kW peak demand",
    },
    "KW30": {
        "name": "KW30 (~30 kW)",
        "best_for": [
            "data centers",
            "hospitals and large healthcare campuses",
            "airports and transportation hubs",
            "manufacturing and heavy industrial plants",
            "large university campuses",
            "full microgrid systems",
            "telecom network hubs",
            "mining operations",
            "oil and gas remote infrastructure",
            "large tribal enterprise campuses",
            "water treatment facilities",
        ],
        "typical_load": "Large — multi-building campus or industrial site with 100+ kW demand",
    },
}

# ── scoring weights (must sum to 100) ─────────────────────────────────────────
SCORING_WEIGHTS = {
    "energy_intensity":      25,   # How energy-hungry is the operation?
    "microgrid_relevance":   25,   # How well does DER/microgrid fit?
    "infrastructure_scale":  20,   # Physical scale of facility/network
    "sustainability_signals": 15,  # ESG / grant / net-zero signals
    "project_immediacy":     15,   # How near-term is the energy activity?
}

HOT_LEAD_THRESHOLD = 85   # leads at or above this score are flagged HOT

# ── data source hints (included in discovery prompts) ────────────────────────
DATA_SOURCE_HINTS = """
Prioritise the following source types when identifying leads:

GOVERNMENT & PUBLIC DATASETS
- DOE microgrid programs and Tribal Energy Program grants
- USDA rural energy / REAP grants
- EPA energy data
- National utility commission filings
- World Bank and AfDB rural electrification programs (Africa)

ENERGY PROJECT DATABASES
- Microgrid project announcements
- Renewable project pipelines
- Interconnection queue filings

NEWS & PRESS RELEASES
- "new data center announced", "microgrid launched", "energy resilience project funded"
- "diesel generator replacement", "off-grid electrification"

INDUSTRY DIRECTORIES
- Utilities, hospitals, universities, industrial facility listings

COMPANY WEBSITES
- Sustainability reports, ESG goals, infrastructure expansion plans
"""

# ── output defaults ───────────────────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = "output"
JSON_OUTPUT_FILENAME = "leads.json"
CSV_OUTPUT_FILENAME  = "leads.csv"
SUMMARY_FILENAME     = "summary.json"
