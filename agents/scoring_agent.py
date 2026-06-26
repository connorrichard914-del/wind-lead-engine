"""
agents/scoring_agent.py

Scoring Agent — Step 3 of the pipeline.

Scores each lead 0–100 across five weighted dimensions using Claude as the
evaluator. Also determines the recommended product (KW20 or KW30).

Score dimensions (from config.SCORING_WEIGHTS):
  energy_intensity      0–25  How energy-hungry is the operation?
  microgrid_relevance   0–25  Alignment with DER / microgrid use cases
  infrastructure_scale  0–20  Physical scale of the facility / network
  sustainability_signals 0–15 ESG / grant / net-zero investment signals
  project_immediacy     0–15  How near-term is the energy project activity?

Total = sum of all dimensions (max 100).
"""

from __future__ import annotations

from utils.claude_client import call_json
from utils.models import Lead, ScoreBreakdown
from utils.logger import log_step, log_warn, log_lead
from data.lead_store import LeadStore
from config import SCORING_WEIGHTS, PRODUCT_CRITERIA, HOT_LEAD_THRESHOLD

# ── system prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """You are a senior energy market analyst scoring B2B leads for a
distributed wind turbine company (KW20 ~20 kW, KW30 ~30 kW).

Score each lead honestly and critically across the five dimensions provided.
Do NOT inflate scores. Reserve 85+ for leads with concrete, near-term energy
investment activity and strong wind/DER alignment. Most leads should score
60–80.

Also determine which product fits better:
- KW20: {kw20_uses}
- KW30: {kw30_uses}
""".format(
    kw20_uses=", ".join(PRODUCT_CRITERIA["KW20"]["best_for"][:5]),
    kw30_uses=", ".join(PRODUCT_CRITERIA["KW30"]["best_for"][:5]),
)

# ── prompt template ───────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """Score the following wind turbine sales lead.

LEAD:
  Company:    {company_name}
  Category:   {category}
  Sub-type:   {sub_category}
  Region:     {region}
  Location:   {location}
  Signals:    {signals}

SCORING DIMENSIONS — assign an integer within each range:
  energy_intensity      0–{w_energy}   (operation's baseline energy demand)
  microgrid_relevance   0–{w_micro}    (DER / distributed generation alignment)
  infrastructure_scale  0–{w_infra}    (physical scale of facility or network)
  sustainability_signals 0–{w_sust}    (ESG / grants / net-zero commitments)
  project_immediacy     0–{w_immed}    (how near-term is actual project activity)

Return a JSON object with EXACTLY these fields:
{{
  "energy_intensity": <int 0–{w_energy}>,
  "microgrid_relevance": <int 0–{w_micro}>,
  "infrastructure_scale": <int 0–{w_infra}>,
  "sustainability_signals": <int 0–{w_sust}>,
  "project_immediacy": <int 0–{w_immed}>,
  "recommended_product": "KW20" or "KW30",
  "recommended_reasoning": "One sentence explaining the product choice"
}}

Return ONLY the JSON object.
"""


def run(store: LeadStore) -> None:
    """
    Score every lead in the store in-place.

    Args:
        store: LeadStore containing enriched leads
    """
    leads = store.all()
    total = len(leads)
    log_step("SCORE", f"Scoring {total} leads")

    for i, lead in enumerate(leads, 1):
        scored = _score_lead(lead)
        if scored:
            store.upsert(scored)
            log_lead(
                scored.company_name,
                scored.lead_score,
                scored.recommended_product,
                scored.region,
            )
        else:
            # Fallback: assign a mid-range score so the lead still exports
            fallback = lead.model_copy(update={"lead_score": 50})
            store.upsert(fallback)

    log_step("SCORE", f"Complete — {total} leads scored")


def _score_lead(lead: Lead) -> Lead | None:
    """Call Claude to score a single lead. Returns updated Lead or None on error."""
    w = SCORING_WEIGHTS
    signals_str = "; ".join(lead.signals_detected) if lead.signals_detected else "none detected"

    prompt = _PROMPT_TEMPLATE.format(
        company_name=lead.company_name,
        category=lead.category,
        sub_category=lead.sub_category,
        region=lead.region,
        location=lead.location,
        signals=signals_str,
        w_energy=w["energy_intensity"],
        w_micro=w["microgrid_relevance"],
        w_infra=w["infrastructure_scale"],
        w_sust=w["sustainability_signals"],
        w_immed=w["project_immediacy"],
    )

    try:
        data = call_json(prompt, system=_SYSTEM, max_tokens=1024)
    except (ValueError, Exception) as exc:
        log_warn(f"Scoring failed for {lead.company_name}: {exc}")
        return None

    if not isinstance(data, dict):
        log_warn(f"Scoring returned non-dict for {lead.company_name}")
        return None

    try:
        breakdown = ScoreBreakdown(
            energy_intensity=_clamp(data.get("energy_intensity", 0), 0, w["energy_intensity"]),
            microgrid_relevance=_clamp(data.get("microgrid_relevance", 0), 0, w["microgrid_relevance"]),
            infrastructure_scale=_clamp(data.get("infrastructure_scale", 0), 0, w["infrastructure_scale"]),
            sustainability_signals=_clamp(data.get("sustainability_signals", 0), 0, w["sustainability_signals"]),
            project_immediacy=_clamp(data.get("project_immediacy", 0), 0, w["project_immediacy"]),
        )
    except Exception as exc:
        log_warn(f"ScoreBreakdown parse error for {lead.company_name}: {exc}")
        return None

    total_score = breakdown.total

    product_raw = str(data.get("recommended_product", "KW30")).upper().strip()
    product = "KW20" if product_raw == "KW20" else "KW30"

    reasoning = str(data.get("recommended_reasoning", "")).strip()

    return lead.model_copy(
        update={
            "lead_score": total_score,
            "score_breakdown": breakdown,
            "recommended_product": product,
            "recommended_reasoning": reasoning,
        }
    )


def _clamp(value: object, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return lo
