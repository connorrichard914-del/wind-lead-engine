"""
agents/enrichment_agent.py

Enrichment Agent — Step 2 of the pipeline.

Adds:
  - Decision makers
  - Additional energy signals
  - Additional sources
  - Contact info (email + phone)
"""

from __future__ import annotations

from typing import Optional

from utils.claude_client import call_json
from utils.models import Lead, DecisionMaker
from utils.logger import log_step, log_warn
from data.lead_store import LeadStore
from config import ENERGY_SIGNALS

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
_SYSTEM = """You are an expert B2B energy infrastructure research assistant.

You enrich company leads for a distributed wind turbine company (KW20 / KW30).

Rules:
- Only use factual or highly likely public information
- Never invent personal contact details
- If unsure about emails or phone numbers, return null
"""

# ─────────────────────────────────────────────
# PROMPT TEMPLATE
# ─────────────────────────────────────────────
_PROMPT_TEMPLATE = """Enrich the following lead for a distributed wind turbine sales pipeline.

LEAD:
  Company: {company_name}
  Category: {category}
  Location: {location}
  Website: {website}
  Known signals: {known_signals}

Return EXACT JSON:

{
  "decision_makers": [
    {"name": "Full Name or Unknown", "role": "Job Title", "linkedin_url": null}
  ],
  "additional_signals": [
    "New energy / infrastructure signal"
  ],
  "additional_sources": [
    "domain.com/page"
  ],
  "contact_info": {
    "email": "generic company email OR null",
    "phone": "main company phone OR null"
  }
}

Rules:
- decision_makers: 2–4 energy decision makers (real or title-based)
- additional_signals: 3–6 new insights not already listed
- additional_sources: 3–5 public URLs (no http/https)
- contact_info:
    - only include publicly visible company contact info
    - NEVER guess personal emails
    - use null if not clearly available
- return ONLY JSON
"""

# ─────────────────────────────────────────────
# MAIN PIPELINE FUNCTION
# ─────────────────────────────────────────────
def run(store: LeadStore) -> None:
    leads = store.all()
    total = len(leads)

    log_step("ENRICH", f"Starting enrichment for {total} leads")

    for i, lead in enumerate(leads, 1):
        log_step("ENRICH", f"[{i}/{total}] {lead.company_name}", region=lead.region)

        enriched = _enrich_lead(lead)
        if enriched:
            store.upsert(enriched)

    log_step("ENRICH", f"Complete — {total} leads enriched")


# ─────────────────────────────────────────────
# SINGLE LEAD ENRICHMENT
# ─────────────────────────────────────────────
def _enrich_lead(lead: Lead) -> Optional[Lead]:

    known_signals = "; ".join(lead.signals_detected) if lead.signals_detected else "none"
    signal_list = "; ".join(ENERGY_SIGNALS)

    prompt = _PROMPT_TEMPLATE.format(
        company_name=lead.company_name,
        category=lead.category,
        location=lead.location,
        website=lead.website,
        known_signals=known_signals,
        signal_list=signal_list,
    )

    try:
        data = call_json(prompt, system=_SYSTEM, max_tokens=2048)
    except Exception as exc:
        log_warn(f"Enrichment failed for {lead.company_name}: {exc}")
        return None

    if not isinstance(data, dict):
        log_warn(f"Invalid enrichment response for {lead.company_name}")
        return None

    # ─────────────────────────────────────────────
    # DECISION MAKERS
    # ─────────────────────────────────────────────
    decision_makers: list[DecisionMaker] = []

    for dm in data.get("decision_makers", []):
        if not isinstance(dm, dict):
            continue

        role = str(dm.get("role", "")).strip()
        if not role:
            continue

        decision_makers.append(
            DecisionMaker(
                name=str(dm.get("name") or "Unknown").strip(),
                role=role,
                linkedin_url=dm.get("linkedin_url"),
            )
        )

    # ─────────────────────────────────────────────
    # SIGNALS MERGE
    # ─────────────────────────────────────────────
    existing = set(lead.signals_detected)

    new_signals = [
        str(s).strip()
        for s in data.get("additional_signals", [])
        if str(s).strip() and str(s).strip() not in existing
    ]

    merged_signals = list(lead.signals_detected) + new_signals

    # ─────────────────────────────────────────────
    # SOURCES MERGE
    # ─────────────────────────────────────────────
    existing_sources = set(lead.sources)

    new_sources = [
        str(s).strip().replace("https://", "").replace("http://", "")
        for s in data.get("additional_sources", [])
        if str(s).strip()
    ]

    merged_sources = list(lead.sources) + [
        s for s in new_sources if s not in existing_sources
    ]

    # ─────────────────────────────────────────────
    # CONTACT INFO (NEW)
    # ─────────────────────────────────────────────
    contact_info = data.get("contact_info", {}) or {}

    email = contact_info.get("email")
    phone = contact_info.get("phone")

    email = str(email).strip() if email else None
    phone = str(phone).strip() if phone else None

    # ─────────────────────────────────────────────
    # RETURN UPDATED LEAD
    # ─────────────────────────────────────────────
    return lead.model_copy(
        update={
            "decision_makers": decision_makers,
            "signals_detected": merged_signals,
            "sources": merged_sources,
            "email": email,
            "phone": phone,
        }
    )