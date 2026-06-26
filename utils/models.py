"""
Pydantic data models for the wind turbine lead discovery engine.
All structured data flowing through the pipeline is validated here.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
# DECISION MAKERS
# ─────────────────────────────────────────────
class DecisionMaker(BaseModel):
    name: str
    role: str
    linkedin_url: Optional[str] = None


# ─────────────────────────────────────────────
# SCORE BREAKDOWN
# ─────────────────────────────────────────────
class ScoreBreakdown(BaseModel):
    energy_intensity: int = Field(ge=0, le=25)
    microgrid_relevance: int = Field(ge=0, le=25)
    infrastructure_scale: int = Field(ge=0, le=20)
    sustainability_signals: int = Field(ge=0, le=15)
    project_immediacy: int = Field(ge=0, le=15)

    @property
    def total(self) -> int:
        return (
            self.energy_intensity
            + self.microgrid_relevance
            + self.infrastructure_scale
            + self.sustainability_signals
            + self.project_immediacy
        )


# ─────────────────────────────────────────────
# MAIN LEAD MODEL
# ─────────────────────────────────────────────
class Lead(BaseModel):
    company_name: str
    category: str
    sub_category: str
    region: Literal["North America", "South America", "Africa"]
    location: str
    website: str

    decision_makers: list[DecisionMaker] = Field(default_factory=list)
    signals_detected: list[str] = Field(default_factory=list)

    why_this_is_a_fit: str = ""

    recommended_product: Literal["KW20", "KW30"] = "KW30"
    recommended_reasoning: str = ""

    lead_score: int = Field(ge=0, le=100, default=0)
    score_breakdown: Optional[ScoreBreakdown] = None

    outreach_angle: str = ""
    sources: list[str] = Field(default_factory=list)

    # ─────────────────────────────────────────────
    # NEW: CONTACT ENRICHMENT FIELDS
    # ─────────────────────────────────────────────
    email: Optional[str] = None
    phone: Optional[str] = None

    # ─────────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────────
    @field_validator("lead_score", mode="before")
    @classmethod
    def clamp_score(cls, v: int) -> int:
        try:
            v = int(v)
        except Exception:
            return 0
        return max(0, min(100, v))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────
    @property
    def is_hot(self) -> bool:
        return self.lead_score >= 85

    def to_export_dict(self) -> dict:
        """Flat dict for CSV/JSON export."""

        base = self.model_dump()

        # flatten score breakdown
        if self.score_breakdown:
            base["score_energy_intensity"] = self.score_breakdown.energy_intensity
            base["score_microgrid_relevance"] = self.score_breakdown.microgrid_relevance
            base["score_infrastructure_scale"] = self.score_breakdown.infrastructure_scale
            base["score_sustainability_signals"] = self.score_breakdown.sustainability_signals
            base["score_project_immediacy"] = self.score_breakdown.project_immediacy

        base.pop("score_breakdown", None)

        # flatten decision makers
        base["decision_makers_flat"] = "; ".join(
            f"{dm['name']} ({dm['role']})"
            for dm in base.get("decision_makers", [])
        )

        base["signals_flat"] = "; ".join(base.get("signals_detected", []))
        base["sources_flat"] = "; ".join(base.get("sources", []))

        return base


# ─────────────────────────────────────────────
# DISCOVERY OUTPUT (pre-enrichment)
# ─────────────────────────────────────────────
class DiscoveryResult(BaseModel):
    company_name: str
    category: str
    sub_category: str
    region: Literal["North America", "South America", "Africa"]
    location: str
    website: str

    initial_signals: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# PIPELINE SUMMARY
# ─────────────────────────────────────────────
class PipelineResult(BaseModel):
    total_leads: int
    hot_leads: int
    average_score: float
    kw20_count: int
    kw30_count: int
    leads_by_region: dict[str, int]
    leads_by_category: dict[str, int]
    leads: list[Lead]

    @classmethod
    def from_leads(cls, leads: list[Lead]) -> "PipelineResult":
        from collections import Counter

        scores = [l.lead_score for l in leads]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0

        return cls(
            total_leads=len(leads),
            hot_leads=sum(1 for l in leads if l.is_hot),
            average_score=avg,
            kw20_count=sum(1 for l in leads if l.recommended_product == "KW20"),
            kw30_count=sum(1 for l in leads if l.recommended_product == "KW30"),
            leads_by_region=dict(Counter(l.region for l in leads)),
            leads_by_category=dict(Counter(l.category for l in leads)),
            leads=sorted(leads, key=lambda l: l.lead_score, reverse=True),
        )