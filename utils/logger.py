"""
Lightweight console logger with colour and structured key=value fields.
No external dependencies — uses only stdlib.
"""

from __future__ import annotations
import sys
from datetime import datetime
from typing import Any


# ANSI colour codes
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_DIM    = "\033[2m"
_MAGENTA = "\033[35m"

_USE_COLOUR = sys.stdout.isatty()


def _colour(code: str, text: str) -> str:
    if not _USE_COLOUR:
        return text
    return f"{code}{text}{_RESET}"


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _fmt_fields(fields: dict[str, Any]) -> str:
    if not fields:
        return ""
    parts = [f"{_colour(_DIM, k + '=')+_colour(_CYAN, str(v))}" for k, v in fields.items()]
    return "  " + "  ".join(parts)


def log_info(msg: str, **fields: Any) -> None:
    prefix = _colour(_GREEN, "INFO ")
    print(f"{_colour(_DIM, _now())}  {prefix}{msg}{_fmt_fields(fields)}")


def log_warn(msg: str, **fields: Any) -> None:
    prefix = _colour(_YELLOW, "WARN ")
    print(f"{_colour(_DIM, _now())}  {prefix}{msg}{_fmt_fields(fields)}", file=sys.stderr)


def log_error(msg: str, **fields: Any) -> None:
    prefix = _colour(_RED, "ERR  ")
    print(f"{_colour(_DIM, _now())}  {prefix}{msg}{_fmt_fields(fields)}", file=sys.stderr)


def log_step(step: str, msg: str, **fields: Any) -> None:
    """Log a pipeline step in bold magenta."""
    prefix = _colour(_BOLD + _MAGENTA, f"[{step}]")
    print(f"{_colour(_DIM, _now())}  {prefix} {msg}{_fmt_fields(fields)}")


def log_lead(company: str, score: int, product: str, region: str) -> None:
    """Pretty-print a single scored lead."""
    hot = _colour(_RED, " 🔥HOT") if score >= 85 else ""
    score_col = _colour(_GREEN if score >= 85 else _YELLOW if score >= 70 else _DIM, f"{score:3d}")
    prod_col = _colour(_CYAN, product)
    print(
        f"  {score_col}/100  {prod_col}  "
        f"{_colour(_BOLD, company[:45]):<45}  "
        f"{_colour(_DIM, region)}{hot}"
    )


def log_separator(title: str = "") -> None:
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        line = "─" * pad + f" {title} " + "─" * pad
    else:
        line = "─" * width
    print(_colour(_DIM, line))


def log_summary(result: Any) -> None:
    """Print pipeline summary stats."""
    log_separator("PIPELINE RESULTS")
    log_info("Total leads",     count=result.total_leads)
    log_info("Hot leads (≥85)", count=result.hot_leads)
    log_info("Average score",   score=result.average_score)
    log_info("KW20 recommended", count=result.kw20_count)
    log_info("KW30 recommended", count=result.kw30_count)
    log_separator("BY REGION")
    for region, count in result.leads_by_region.items():
        log_info(region, leads=count)
    log_separator("BY CATEGORY")
    for cat, count in sorted(result.leads_by_category.items(), key=lambda x: -x[1]):
        log_info(cat, leads=count)
    log_separator()
