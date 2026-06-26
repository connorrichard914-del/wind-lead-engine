"""
agents/discovery_agent.py

Discovery Agent — Step 1 of the pipeline.

Queries Claude to generate a batch of raw lead candidates for a given
region and buyer category. Returns a list of DiscoveryResult objects
ready for the enrichment stage.

Design notes:
- One Claude call per (region, category) pair so prompts stay focused
- Validates every field; silently drops malformed entries
- Caller controls how many leads to request per batch
"""

from __future__ import annotations

import json
from typing import Optional

from utils.claude_client import call_json
from utils.models import DiscoveryResult
from utils.logger import log_step, log_warn, log_info
from config import (
    BUYER_CATEGORIES,
    REGIONS,
    ENERGY_SIGNALS,
    DATA_SOURCE_HINTS,
    PRODUCT_CRITERIA,
)

# ── system prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """You are a B2B lead research specialist for a company that sells
distributed wind turbines (KW20 ~20 kW and KW30 ~30 kW) for microgrids,
behind-the-meter generation, and energy resilience projects.

Your job is to identify REAL companies and organisations that are active
energy buyers likely to invest in distributed wind generation.

{data_source_hints}

Energy buyer signals to look for:
{signals}

Product context:
- KW20: {kw20_best_for}
- KW30: {kw30_best_for}
""".format(
    data_source_hints=DATA_SOURCE_HINTS,
    signals="\n".join(f"  • {s}" for s in ENERGY_SIGNALS),
    kw20_best_for=", ".join(PRODUCT_CRITERIA["KW20"]["best_for"]),
    kw30_best_for=", ".join(PRODUCT_CRITERIA["KW30"]["best_for"]),
)

# ── prompt template ───────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """Identify {n} high-quality lead companies or organisations
in the following scope:

REGION: {region}
BUYER CATEGORY: {category}

Return a JSON array where each element has EXACTLY these fields:
{{
  "company_name": "Full legal or trading name",
  "category": "{category_short}",
  "sub_category": "Specific sub-type within the category",
  "region": "{region}",
  "location": "City, State/Province, Country",
  "website": "domain.com (no https://)",
  "initial_signals": ["signal 1", "signal 2", ...],
  "sources": ["source1.com/path", "source2.org/path"]
}}

Rules:
- All companies must be real, named, verifiable organisations
- Prioritise organisations with ACTIVE energy investment signals
- Spread across different countries within {region}
- initial_signals must be specific to THIS company, not generic
- Include 2–4 source URLs per lead (no https:// prefix)
- Return ONLY the JSON array, no commentary
"""


def run(
    regions: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    leads_per_batch: int = 3,
) -> list[DiscoveryResult]:
    """
    Discover raw lead candidates.

    Args:
        regions:          Subset of REGIONS to target (default: all)
        categories:       Subset of BUYER_CATEGORIES to target (default: all)
        leads_per_batch:  How many leads to request per (region, category) call

    Returns:
        Deduplicated list of DiscoveryResult objects
    """
    target_regions = regions or REGIONS
    target_categories = categories or BUYER_CATEGORIES

    all_results: list[DiscoveryResult] = []
    seen_names: set[str] = set()

    total_batches = len(target_regions) * len(target_categories)
    batch_num = 0

    for region in target_regions:
        for category in target_categories:
            batch_num += 1
            # Derive a short label for the category field
            category_short = _short_label(category)

            log_step(
                "DISCOVER",
                f"batch {batch_num}/{total_batches}",
                region=region,
                category=category_short,
                n=leads_per_batch,
            )

            prompt = _PROMPT_TEMPLATE.format(
                n=leads_per_batch,
                region=region,
                category=category,
                category_short=category_short,
            )

            try:
                raw_list = call_json(prompt, system=_SYSTEM, max_tokens=4096)
            except (ValueError, Exception) as exc:
                log_warn(f"Discovery batch failed — skipping", region=region, category=category_short, error=str(exc))
                continue

            if not isinstance(raw_list, list):
                log_warn("Claude returned non-list for discovery batch", region=region)
                continue

            batch_accepted = 0
            for item in raw_list:
                result = _parse_item(item, region, category_short)
                if result is None:
                    continue
                # Deduplicate within this discovery run
                key = result.company_name.lower().strip()
                if key in seen_names:
                    continue
                seen_names.add(key)
                all_results.append(result)
                batch_accepted += 1

            log_info(f"Accepted {batch_accepted}/{len(raw_list)} leads from batch")

    log_step("DISCOVER", f"Complete — {len(all_results)} raw leads found")
    return all_results


def _parse_item(item: dict, region: str, category_short: str) -> Optional[DiscoveryResult]:
    """Validate and coerce a raw dict into a DiscoveryResult. Returns None on failure."""
    if not isinstance(item, dict):
        return None

    try:
        # Coerce region to the canonical value (Claude may return slight variants)
        item_region = item.get("region", region)
        if item_region not in REGIONS:
            item_region = region

        return DiscoveryResult(
            company_name=str(item.get("company_name", "")).strip(),
            category=str(item.get("category", category_short)).strip(),
            sub_category=str(item.get("sub_category", "")).strip(),
            region=item_region,  # type: ignore[arg-type]
            location=str(item.get("location", "")).strip(),
            website=str(item.get("website", "")).strip().lstrip("https://").lstrip("http://"),
            initial_signals=[str(s) for s in item.get("initial_signals", []) if s],
            sources=[str(s) for s in item.get("sources", []) if s],
        )
    except Exception as exc:
        log_warn(f"Could not parse discovery item: {exc}", name=item.get("company_name", "?"))
        return None


def _short_label(full_category: str) -> str:
    """Map a full BUYER_CATEGORIES string to a compact label."""
    mapping = {
        "Microgrid developers/operators": "Microgrid",
        "Data centers": "Data Center",
        "Rural electric cooperatives": "Rural Electric",
        "Tribal nations / indigenous energy programs": "Tribal",
        "Agriculture (farms, irrigation, food processing)": "Agriculture",
        "Hospitals / healthcare systems": "Hospital",
        "Universities / campuses": "University",
        "Manufacturing / industrial facilities": "Manufacturing",
        "Airports / transportation hubs": "Airport",
        "Military / government facilities": "Military / Government",
        "Telecom / remote infrastructure": "Telecom",
        "Battery storage / renewable developers": "Battery Storage / Renewable",
        "Water treatment / utilities": "Water Treatment",
        "Mining / oil & gas remote operations": "Mining / Oil & Gas",
    }
    return mapping.get(full_category, full_category.split("/")[0].strip())
