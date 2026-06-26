"""
agents/qualification_agent.py

Qualification Agent — Step 4 (final) of the pipeline.

For each scored lead, generates:
  - why_this_is_a_fit  : 2–4 sentence explanation of the strategic fit
  - outreach_angle     : 2–3 sentence personalised first-contact message angle

These are the human-readable outputs that sales reps use directly.
One Claude call per lead.
"""

from __future__ import annotations

from utils.claude_client import call_json
from utils.models import Lead
from utils.logger import log_step, log_warn
from data.lead_store import LeadStore
from config import PRODUCT_CRITERIA

# ── system prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """You are a senior sales strategist for a company that makes
distributed wind turbines: KW20 (~20 kW) and KW30 (~30 kW) for microgrids,
behind-the-meter generation, and energy resilience projects.

Write with the voice of a knowledgeable energy consultant, not a salesperson.
Be specific to the company — reference their real signals, location, and
context. Never use generic language like "innovative solution" or "cutting-edge".

KW20 is best for: {kw20}
KW30 is best for: {kw30}
""".format(
    kw20=", ".join(PRODUCT_CRITERIA["KW20"]["best_for"]),
    kw30=", ".join(PRODUCT_CRITERIA["KW30"]["best_for"]),
)

# ── prompt template ───────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """Write qualification copy for this wind turbine sales lead.

LEAD:
  Company:             {company_name}
  Category:            {category}
  Location:            {location}
  Region:              {region}
  Signals detected:    {signals}
  Recommended product: {product}
  Product reasoning:   {reasoning}
  Lead score:          {score}/100

Return a JSON object with EXACTLY these two fields:

{{
  "why_this_is_a_fit": "2–4 sentences explaining WHY this company is a strong
    fit for distributed wind. Reference their specific context, signals, and
    geographic wind resource. Be concrete and factual.",

  "outreach_angle": "2–3 sentences for a cold outreach message to the primary
    decision maker. Reference their specific pain point or goal, explain what
    the {product} does for them specifically, and close with a business case
    hook (ROI, compliance, resilience, sovereignty, etc.)."
}}

Return ONLY the JSON object.
"""


def run(store: LeadStore) -> None:
    """
    Generate qualification copy for every lead in the store in-place.

    Args:
        store: LeadStore containing scored leads
    """
    leads = store.all()
    total = len(leads)
    log_step("QUALIFY", f"Generating qualification copy for {total} leads")

    for i, lead in enumerate(leads, 1):
        log_step("QUALIFY", f"[{i}/{total}] {lead.company_name}")
        qualified = _qualify_lead(lead)
        if qualified:
            store.upsert(qualified)

    log_step("QUALIFY", f"Complete — {total} leads qualified")


def _qualify_lead(lead: Lead) -> Lead | None:
    """Call Claude to write qualification copy for a single lead."""
    signals_str = "; ".join(lead.signals_detected) if lead.signals_detected else "general energy investment interest"

    prompt = _PROMPT_TEMPLATE.format(
        company_name=lead.company_name,
        category=lead.category,
        location=lead.location,
        region=lead.region,
        signals=signals_str,
        product=lead.recommended_product,
        reasoning=lead.recommended_reasoning or "fits the scale and use case",
        score=lead.lead_score,
    )

    try:
        data = call_json(prompt, system=_SYSTEM, max_tokens=1024)
    except (ValueError, Exception) as exc:
        log_warn(f"Qualification failed for {lead.company_name}: {exc}")
        return None

    if not isinstance(data, dict):
        log_warn(f"Qualification returned non-dict for {lead.company_name}")
        return None

    why = str(data.get("why_this_is_a_fit", "")).strip()
    outreach = str(data.get("outreach_angle", "")).strip()

    if not why or not outreach:
        log_warn(f"Empty qualification copy for {lead.company_name}")
        return None

    return lead.model_copy(
        update={
            "why_this_is_a_fit": why,
            "outreach_angle": outreach,
        }
    )
