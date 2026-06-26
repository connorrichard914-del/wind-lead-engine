"""
exporters/csv_exporter.py

CSV Exporter — writes two flat CSV files to the output directory:

  leads.csv      — all leads, one row per lead, all fields flattened
  hot_leads.csv  — only leads scoring >= HOT_LEAD_THRESHOLD

Nested structures (decision_makers, signals, sources, score_breakdown)
are flattened into semicolon-delimited strings or separate columns
so the file opens cleanly in Excel / Google Sheets.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from utils.models import PipelineResult, Lead
from utils.logger import log_info, log_step
from config import DEFAULT_OUTPUT_DIR, CSV_OUTPUT_FILENAME, HOT_LEAD_THRESHOLD


# Ordered column list — determines CSV column order
_COLUMNS = [
    "rank",
    "lead_score",
    "is_hot",
    "company_name",
    "category",
    "sub_category",
    "region",
    "location",
    "website",
    "recommended_product",
    "recommended_reasoning",
    "why_this_is_a_fit",
    "outreach_angle",
    "decision_makers",
    "signals_detected",
    "sources",
    # Score breakdown columns
    "score_energy_intensity",
    "score_microgrid_relevance",
    "score_infrastructure_scale",
    "score_sustainability_signals",
    "score_project_immediacy",
]


def run(result: PipelineResult, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    """
    Write all CSV output files.

    Args:
        result:     Completed PipelineResult
        output_dir: Directory to write files into (created if absent)

    Returns:
        Dict mapping file role → absolute file path
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    log_step("EXPORT", f"Writing CSV files to {out.resolve()}")

    paths: dict[str, str] = {}

    # 1. Full lead CSV
    leads_path = out / CSV_OUTPUT_FILENAME
    _write_csv(result.leads, leads_path)
    paths["leads_csv"] = str(leads_path.resolve())
    log_info("Wrote leads CSV", path=str(leads_path), rows=len(result.leads))

    # 2. Hot leads CSV
    hot_leads = [l for l in result.leads if l.lead_score >= HOT_LEAD_THRESHOLD]
    if hot_leads:
        hot_path = out / "hot_leads.csv"
        _write_csv(hot_leads, hot_path)
        paths["hot_leads_csv"] = str(hot_path.resolve())
        log_info("Wrote hot leads CSV", path=str(hot_path), rows=len(hot_leads))

    return paths


# ── helpers ───────────────────────────────────────────────────────────────────

def _flatten_lead(lead: Lead, rank: int) -> dict:
    """Convert a Lead to a flat dict matching _COLUMNS."""
    sb = lead.score_breakdown

    # Flatten decision makers: "Name (Role); Name (Role)"
    dm_str = "; ".join(
        f"{dm.name} ({dm.role})" for dm in lead.decision_makers
    )

    return {
        "rank":                        rank,
        "lead_score":                  lead.lead_score,
        "is_hot":                      "YES" if lead.is_hot else "no",
        "company_name":                lead.company_name,
        "category":                    lead.category,
        "sub_category":                lead.sub_category,
        "region":                      lead.region,
        "location":                    lead.location,
        "website":                     lead.website,
        "recommended_product":         lead.recommended_product,
        "recommended_reasoning":       lead.recommended_reasoning,
        "why_this_is_a_fit":           lead.why_this_is_a_fit,
        "outreach_angle":              lead.outreach_angle,
        "decision_makers":             dm_str,
        "signals_detected":            "; ".join(lead.signals_detected),
        "sources":                     "; ".join(lead.sources),
        # Score breakdown — empty string if scoring didn't run
        "score_energy_intensity":      sb.energy_intensity if sb else "",
        "score_microgrid_relevance":   sb.microgrid_relevance if sb else "",
        "score_infrastructure_scale":  sb.infrastructure_scale if sb else "",
        "score_sustainability_signals": sb.sustainability_signals if sb else "",
        "score_project_immediacy":     sb.project_immediacy if sb else "",
    }


def _write_csv(leads: list[Lead], path: Path) -> None:
    """Write a list of leads to a CSV file at path."""
    rows = [_flatten_lead(lead, rank) for rank, lead in enumerate(leads, 1)]

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        # utf-8-sig adds BOM so Excel opens it correctly without import wizard
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
