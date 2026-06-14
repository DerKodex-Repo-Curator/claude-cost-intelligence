"""Insight synthesis: assemble the canonical CCI report object.

Combines analytics + waste detection into one JSON-serializable dict that the
terminal report, the HTML dashboard, and ``--json`` all render from. Also
generates the headline "holy crap" cards (the screenshot-worthy summary).
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import __version__
from .analytics import Analysis, analyze
from .normalize import Event
from .waste import WasteReport, detect


def _headline(an: Analysis, waste: WasteReport) -> list[dict]:
    """Three or four punchy facts for the top of the dashboard."""
    cards = []
    span = an.meta.get("span_days") or 1
    cards.append({
        "label": "Total spend",
        "value": f"${an.totals['cost']:,.2f}",
        "sub": f"{span} day(s) · {an.totals['requests']:,} requests · {an.totals['sessions']:,} sessions",
        "tone": "neutral",
    })
    if waste.recoverable_mid > 0:
        cards.append({
            "label": "Estimated recoverable",
            "value": f"${waste.recoverable_mid:,.2f}",
            "sub": f"~{waste.recoverable_pct*100:.0f}% of spend · band ${waste.recoverable_low:,.0f}–${waste.recoverable_high:,.0f}",
            "tone": "good",
        })
    p = an.pareto
    if p["sessions_total"] >= 4:
        cards.append({
            "label": "Concentration",
            "value": f"{p['sessions_to_half']} session(s)",
            "sub": f"drive ~50% of spend · top one = {p['top1_share']*100:.0f}%",
            "tone": "warn",
        })
    if an.by_model:
        top = an.by_model[0]
        share = top["cost"] / (an.totals["cost"] or 1e-12)
        avg_share = 1.0 / max(1, an.totals["models"])
        x = share / avg_share if avg_share else 1.0
        cards.append({
            "label": "Top model",
            "value": top["key"].replace("claude-", ""),
            "sub": f"{share*100:.0f}% of spend · {x:.1f}x its even share",
            "tone": "warn" if x >= 1.5 else "neutral",
        })
    return cards


def build_report(events: list[Event], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    an = analyze(events, now)
    waste = detect(events, an)
    report = {
        "schema": "cci/report@1",
        "version": __version__,
        "generated_at": now.isoformat(),
        "meta": an.meta,
        "totals": an.totals,
        "headline": _headline(an, waste),
        "by_model": an.by_model,
        "by_project": an.by_project,
        "daily": an.daily,
        "sessions": an.sessions,
        "pareto": an.pareto,
        "projection": an.projection,
        "waste": waste.as_dict(),
    }
    return report
