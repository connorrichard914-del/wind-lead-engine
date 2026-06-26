"""
main.py — Wind Turbine Lead Discovery Engine
============================================

Entry point for the full pipeline:
  1. Discovery  — find raw lead candidates via Claude
  2. Enrichment — add decision makers, signals, sources
  3. Scoring    — score 0–100 across 5 dimensions, recommend KW20/KW30
  4. Qualification — write why_this_is_a_fit + outreach_angle copy
  5. Export     — write JSON and/or CSV to ./output/

Usage:
  python main.py                         # full run, all regions, all categories
  python main.py --region "Africa"       # single region
  python main.py --category "Mining"     # single category (partial match)
  python main.py --leads 2              # leads per (region × category) batch
  python main.py --output json          # json only
  python main.py --output csv           # csv only
  python main.py --hot-only             # print hot leads summary to stdout
  python main.py --skip-export          # run pipeline, skip file writing
  python main.py --output-dir results   # custom output directory

Requires:
  ANTHROPIC_API_KEY environment variable (or set in .env)
  pip install anthropic python-dotenv pydantic
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ── load .env before any other imports that read env vars ─────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; ANTHROPIC_API_KEY can be set in shell

# ── project imports ───────────────────────────────────────────────────────────
# Add the project root to sys.path so sub-packages resolve correctly when
# running as `python main.py` from the project root.
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import REGIONS, BUYER_CATEGORIES, DEFAULT_OUTPUT_DIR, HOT_LEAD_THRESHOLD
from data.lead_store import LeadStore
from utils.models import PipelineResult
from utils.logger import (
    log_info, log_step, log_separator, log_summary, log_lead, log_warn, log_error,
)

import agents.discovery_agent     as discovery_agent
import agents.enrichment_agent    as enrichment_agent
import agents.scoring_agent       as scoring_agent
import agents.qualification_agent as qualification_agent
import exporters.json_exporter    as json_exporter
import exporters.csv_exporter     as csv_exporter


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Wind Turbine Lead Discovery Engine — discovers, scores, and exports B2B leads.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--region",
        choices=REGIONS,
        default=None,
        metavar="REGION",
        help=f"Limit discovery to one region. Choices: {', '.join(REGIONS)}",
    )
    p.add_argument(
        "--category",
        default=None,
        metavar="CATEGORY",
        help="Limit discovery to categories containing this string (partial match, case-insensitive).",
    )
    p.add_argument(
        "--leads",
        type=int,
        default=2,
        metavar="N",
        help="Number of leads to request per (region × category) batch. Default: 2",
    )
    p.add_argument(
        "--output",
        choices=["json", "csv", "both"],
        default="both",
        help="Output format. Default: both",
    )
    p.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory for output files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    p.add_argument(
        "--hot-only",
        action="store_true",
        help=f"After pipeline, print only hot leads (score >= {HOT_LEAD_THRESHOLD}) to stdout.",
    )
    p.add_argument(
        "--skip-export",
        action="store_true",
        help="Run the full pipeline but skip writing files.",
    )
    p.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip the enrichment stage (faster, less data).",
    )
    p.add_argument(
        "--skip-qualification",
        action="store_true",
        help="Skip the qualification stage (no outreach copy generated).",
    )
    return p


# ── pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(args: argparse.Namespace) -> PipelineResult:
    """Execute all pipeline stages and return a PipelineResult."""

    store = LeadStore()

    # ── resolve filters ───────────────────────────────────────────────────────
    regions = [args.region] if args.region else REGIONS

    if args.category:
        cat_lower = args.category.lower()
        categories = [c for c in BUYER_CATEGORIES if cat_lower in c.lower()]
        if not categories:
            log_warn(
                f"No categories matched '{args.category}'. Using all categories.",
            )
            categories = BUYER_CATEGORIES
    else:
        categories = BUYER_CATEGORIES

    log_separator("WIND TURBINE LEAD DISCOVERY ENGINE")
    log_info("Regions",    regions=", ".join(regions))
    log_info("Categories", count=len(categories))
    log_info("Leads/batch", n=args.leads)
    log_separator()

    # ── STAGE 1: Discovery ────────────────────────────────────────────────────
    t0 = time.time()
    log_step("1/4", "DISCOVERY")

    raw_leads = discovery_agent.run(
        regions=regions,
        categories=categories,
        leads_per_batch=args.leads,
    )

    if not raw_leads:
        log_error("Discovery returned no leads. Check your ANTHROPIC_API_KEY and network.")
        sys.exit(1)

    # Ingest into store (deduplication happens here)
    for raw in raw_leads:
        store.add_discovery(raw)

    log_info(f"Store after discovery", total=len(store))
    log_separator()

    # ── STAGE 2: Enrichment ───────────────────────────────────────────────────
    if not args.skip_enrichment:
        log_step("2/4", "ENRICHMENT")
        enrichment_agent.run(store)
        log_separator()
    else:
        log_info("Enrichment skipped (--skip-enrichment)")

    # ── STAGE 3: Scoring ──────────────────────────────────────────────────────
    log_step("3/4", "SCORING")
    scoring_agent.run(store)
    log_separator()

    # ── STAGE 4: Qualification ────────────────────────────────────────────────
    if not args.skip_qualification:
        log_step("4/4", "QUALIFICATION")
        qualification_agent.run(store)
        log_separator()
    else:
        log_info("Qualification skipped (--skip-qualification)")

    # ── build result ──────────────────────────────────────────────────────────
    result = PipelineResult.from_leads(store.ranked())
    elapsed = time.time() - t0
    log_info(f"Pipeline complete", elapsed_s=f"{elapsed:.1f}s")

    return result


# ── export ────────────────────────────────────────────────────────────────────

def export(result: PipelineResult, args: argparse.Namespace) -> None:
    """Write output files based on --output flag."""
    if args.skip_export:
        log_info("Export skipped (--skip-export)")
        return

    log_separator("EXPORT")
    output_dir = args.output_dir
    exported_paths: dict[str, str] = {}

    if args.output in ("json", "both"):
        paths = json_exporter.run(result, output_dir=output_dir)
        exported_paths.update(paths)

    if args.output in ("csv", "both"):
        paths = csv_exporter.run(result, output_dir=output_dir)
        exported_paths.update(paths)

    log_separator()
    log_info("Output files written:")
    for role, path in exported_paths.items():
        log_info(f"  {role}", path=path)


# ── hot leads display ─────────────────────────────────────────────────────────

def print_hot_leads(result: PipelineResult) -> None:
    hot = [l for l in result.leads if l.lead_score >= HOT_LEAD_THRESHOLD]
    if not hot:
        log_info(f"No hot leads found (threshold: {HOT_LEAD_THRESHOLD})")
        return

    log_separator(f"HOT LEADS — score >= {HOT_LEAD_THRESHOLD}")
    for lead in hot:
        log_lead(lead.company_name, lead.lead_score, lead.recommended_product, lead.region)
        if lead.outreach_angle:
            print(f"     → {lead.outreach_angle[:120]}{'...' if len(lead.outreach_angle) > 120 else ''}")
        print()
    log_separator()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Verify API key early for a clear error message
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log_error(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to a .env file in this directory or export it in your shell:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    try:
        result = run_pipeline(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted — exiting.")
        sys.exit(130)
    except Exception as exc:
        log_error(f"Pipeline failed: {exc}")
        raise

    # Print summary table
    log_summary(result)

    # Optionally highlight hot leads
    if args.hot_only or result.hot_leads > 0:
        print_hot_leads(result)

    # Write files
    export(result, args)


if __name__ == "__main__":
    main()
