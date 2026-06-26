"""
data/lead_store.py

In-memory lead store with deduplication, filtering, and ranked retrieval.
Acts as the shared state that all pipeline agents read from and write to.
"""

from __future__ import annotations

import re
from typing import Optional

from utils.models import Lead, DiscoveryResult
from utils.logger import log_info, log_warn


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — used for dedup keys."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


class LeadStore:
    """
    Thread-safe-enough (single-process) store for all Lead objects.

    Responsibilities:
    - Accept raw DiscoveryResult objects and promote them to Lead stubs
    - Deduplicate by normalised company name
    - Allow in-place updates as agents enrich, score, and qualify each lead
    - Provide filtered / sorted views for export
    """

    def __init__(self) -> None:
        # Ordered list preserves insertion sequence; dict provides O(1) lookup
        self._leads: dict[str, Lead] = {}   # dedup_key → Lead

    # ── ingestion ─────────────────────────────────────────────────────────────

    def add_discovery(self, raw: DiscoveryResult) -> Optional[Lead]:
        """
        Convert a DiscoveryResult into a Lead stub and store it.
        Returns the new Lead, or None if it was a duplicate.
        """
        key = _normalise(raw.company_name)
        if key in self._leads:
            log_warn("Duplicate lead skipped", company=raw.company_name)
            return None

        lead = Lead(
            company_name=raw.company_name,
            category=raw.category,
            sub_category=raw.sub_category,
            region=raw.region,
            location=raw.location,
            website=raw.website,
            signals_detected=list(raw.initial_signals),
            sources=list(raw.sources),
        )
        self._leads[key] = lead
        return lead

    def upsert(self, lead: Lead) -> None:
        """Replace or insert a Lead by normalised company name."""
        key = _normalise(lead.company_name)
        self._leads[key] = lead

    # ── retrieval ─────────────────────────────────────────────────────────────

    def get(self, company_name: str) -> Optional[Lead]:
        return self._leads.get(_normalise(company_name))

    def all(self) -> list[Lead]:
        """Return all leads in insertion order."""
        return list(self._leads.values())

    def ranked(self) -> list[Lead]:
        """Return all leads sorted by score descending."""
        return sorted(self._leads.values(), key=lambda l: l.lead_score, reverse=True)

    def hot(self, threshold: int = 85) -> list[Lead]:
        """Return leads at or above threshold, sorted by score descending."""
        return [l for l in self.ranked() if l.lead_score >= threshold]

    def by_region(self, region: str) -> list[Lead]:
        return [l for l in self._leads.values() if l.region == region]

    def by_category(self, category: str) -> list[Lead]:
        """Partial, case-insensitive category match."""
        cat_lower = category.lower()
        return [l for l in self._leads.values() if cat_lower in l.category.lower()]

    def filter(
        self,
        region: Optional[str] = None,
        category: Optional[str] = None,
        min_score: int = 0,
        product: Optional[str] = None,
    ) -> list[Lead]:
        results = self._leads.values()
        if region:
            results = [l for l in results if l.region == region]
        if category:
            cat_lower = category.lower()
            results = [l for l in results if cat_lower in l.category.lower()]
        if min_score:
            results = [l for l in results if l.lead_score >= min_score]
        if product:
            results = [l for l in results if l.recommended_product == product.upper()]
        return sorted(results, key=lambda l: l.lead_score, reverse=True)

    # ── stats ─────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._leads)

    def stats(self) -> dict:
        leads = self.all()
        if not leads:
            return {"total": 0}
        scores = [l.lead_score for l in leads]
        from collections import Counter
        return {
            "total": len(leads),
            "hot": sum(1 for l in leads if l.is_hot),
            "avg_score": round(sum(scores) / len(scores), 1),
            "max_score": max(scores),
            "min_score": min(scores),
            "by_region": dict(Counter(l.region for l in leads)),
            "by_product": dict(Counter(l.recommended_product for l in leads)),
            "by_category": dict(Counter(l.category for l in leads)),
        }

    def log_stats(self) -> None:
        s = self.stats()
        log_info(
            "LeadStore stats",
            total=s["total"],
            hot=s.get("hot", 0),
            avg_score=s.get("avg_score", 0),
        )
