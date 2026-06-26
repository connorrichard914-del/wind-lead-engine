"""
exporters/json_exporter.py

JSON Exporter — writes three JSON files to the output directory:

  leads.json     — full ranked lead array (all fields)
  summary.json   — pipeline stats + hot lead list
  hot_leads.json — only leads scoring >= HOT_LEAD_THRESHOLD
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from utils.models import PipelineResult, Lead
from utils.logger import log_info, log_step
from config import (
    DEFAULT_OUTPUT_DIR,
    JSON_OUTPUT_FILENAME,
    SUMMARY_FILENAME,
    HOT_LEAD_THRESHOLD,
)


def run(result: PipelineResult, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    """
    Write all JSON output files.

    Args:
        result:     Completed PipelineResult
        output_dir: Directory to write files into (created if absent)

    Returns:
        Dict mapping file role → absolute file path
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    log_step("EXPORT", f"Writing JSON files to {out.resolve()}")

    paths: dict[str, str] = {}

    # 1. Full lead array
    leads_path = out / JSON_OUTPUT_FILENAME
    _write_leads(result.leads, leads_path)
    paths["leads"] = str(leads_path.resolve())
    log_info("Wrote leads JSON", path=str(leads_path), count=len(result.leads))

    # 2. Summary + stats
    summary_path = out / SUMMARY_FILENAME
    _write_summary(result, summary_path)
    paths["summary"] = str(summary_path.resolve())
    log_info("Wrote summary JSON", path=str(summary_path))

    # 3. Hot leads only
    hot_leads = [l for l in result.leads if l.lead_score >= HOT_LEAD_THRESHOLD]
    if hot_leads:
        hot_path = out / "hot_leads.json"
        _write_leads(hot_leads, hot_path)
        paths["hot_leads"] = str(hot_path.resolve())
        log_info("Wrote hot leads JSON", path=str(hot_path), count=len(hot_leads))

    return paths


# ── helpers ───────────────────────────────────────────────────────────────────

def _serialise_lead(lead: Lead) -> dict:
    """Convert a Lead to a JSON-serialisable dict, preserving all nested structure."""
    d = lead.model_dump()

    # Convert ScoreBreakdown object → flat sub-dict
    if lead.score_breakdown:
        d["score_breakdown"] = {
            "energy_intensity":       lead.score_breakdown.energy_intensity,
            "microgrid_relevance":    lead.score_breakdown.microgrid_relevance,
            "infrastructure_scale":   lead.score_breakdown.infrastructure_scale,
            "sustainability_signals": lead.score_breakdown.sustainability_signals,
            "project_immediacy":      lead.score_breakdown.project_immediacy,
            "total":                  lead.score_breakdown.total,
        }

    # Convert DecisionMaker objects → list of dicts
    d["decision_makers"] = [
        {
            "name":         dm.name,
            "role":         dm.role,
            "linkedin_url": dm.linkedin_url,
        }
        for dm in lead.decision_makers
    ]

    return d


def _write_leads(leads: list[Lead], path: Path) -> None:
    payload = [_serialise_lead(l) for l in leads]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def _write_summary(result: PipelineResult, path: Path) -> None:
    hot_leads_preview = [
        {
            "company_name":       l.company_name,
            "category":           l.category,
            "region":             l.region,
            "location":           l.location,
            "lead_score":         l.lead_score,
            "recommended_product": l.recommended_product,
            "outreach_angle":     l.outreach_angle,
        }
        for l in result.leads
        if l.lead_score >= HOT_LEAD_THRESHOLD
    ]

    summary = {
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "total_leads":        result.total_leads,
        "hot_leads":          result.hot_leads,
        "average_score":      result.average_score,
        "kw20_recommended":   result.kw20_count,
        "kw30_recommended":   result.kw30_count,
        "leads_by_region":    result.leads_by_region,
        "leads_by_category":  result.leads_by_category,
        "hot_lead_threshold": HOT_LEAD_THRESHOLD,
        "hot_leads_preview":  hot_leads_preview,
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
