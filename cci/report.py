"""Terminal report renderer — the ``cci report`` view.

Self-contained ANSI rendering (no rich/colorama dependency). Honors NO_COLOR
and non-tty output by degrading to plain text.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
_COL = {
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "mag": "\033[35m", "blue": "\033[34m", "grey": "\033[90m",
}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CCI_FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


class _Pen:
    def __init__(self, enabled: bool):
        self.on = enabled

    def __call__(self, text: str, *codes: str) -> str:
        if not self.on or not codes:
            return text
        prefix = "".join(_COL.get(c, c) for c in codes)
        return f"{prefix}{text}{RESET}"


def _bar(frac: float, width: int = 24) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "█" * filled + "·" * (width - filled)


def _money(x: float) -> str:
    return f"${x:,.2f}" if abs(x) >= 0.005 else f"${x:.4f}"


def _ktok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def render(report: dict, budget: dict | None = None, color: bool | None = None) -> str:
    pen = _Pen(_use_color() if color is None else color)
    t = report["totals"]
    out: list[str] = []
    w = 64

    def rule(ch="─"):
        out.append(pen(ch * w, "grey"))

    # ---- header ----
    out.append("")
    out.append(pen("  CLAUDE COST INTELLIGENCE", BOLD, "cyan"))
    meta = report["meta"]
    span = meta.get("span_days") or 0
    rng = ""
    if meta.get("start") and meta.get("end"):
        rng = f"{meta['start'][:10]} → {meta['end'][:10]}  ({span}d)"
    out.append(pen(f"  {rng}", "grey"))
    rule()

    # ---- headline cards ----
    for c in report["headline"]:
        tone = {"good": "green", "warn": "yellow", "neutral": "cyan"}.get(c["tone"], "cyan")
        out.append(f"  {pen(c['value'], BOLD, tone):<24}  {pen(c['label'], 'grey')}")
        out.append(f"  {pen(c['sub'], DIM)}")
    rule()

    # ---- spend by model ----
    out.append(pen("  SPEND BY MODEL", BOLD))
    total = t["cost"] or 1e-12
    for m in report["by_model"][:8]:
        frac = m["cost"] / total
        name = m["key"].replace("claude-", "")[:22]
        flag = pen(" (unpriced)", "red") if m["unpriced"] else ""
        out.append(
            f"  {name:<22} {pen(_bar(frac, 18), 'mag')} "
            f"{_money(m['cost']):>9} {pen(f'{frac*100:4.0f}%', 'grey')}{flag}"
        )
    rule()

    # ---- top projects ----
    if len(report["by_project"]) > 1:
        out.append(pen("  SPEND BY PROJECT", BOLD))
        for p in report["by_project"][:6]:
            frac = p["cost"] / total
            out.append(
                f"  {p['key'][:22]:<22} {pen(_bar(frac, 18), 'blue')} "
                f"{_money(p['cost']):>9} {pen(f'{frac*100:4.0f}%', 'grey')}"
            )
        rule()

    # ---- top sessions ----
    out.append(pen("  TOP SESSIONS BY COST", BOLD))
    for s in report["sessions"][:6]:
        sid = s["session_id"][:8]
        req = pen(f"{s['requests']:>3} req", "grey")
        tok = pen(f"{_ktok(s['tokens'])} tok", "grey")
        out.append(
            f"  {pen(sid, 'cyan')} {s['project'][:16]:<16} "
            f"{_money(s['cost']):>9}  {req} {tok}"
        )
    rule()

    # ---- waste / savings ----
    waste = report["waste"]
    title = pen("  OPTIMIZATION — ", BOLD) + pen(
        f"est. recoverable {_money(waste['recoverable_mid'])} "
        f"({waste['recoverable_pct']*100:.0f}%)", BOLD, "green"
    )
    out.append(title)
    out.append(pen(
        f"  band {_money(waste['recoverable_low'])}–{_money(waste['recoverable_high'])}  "
        "· estimates, not guarantees", DIM))
    out.append("")
    for f in waste["findings"]:
        icon = {"savings": "💸", "attention": "🔎", "data": "ℹ️"}.get(f["kind"], "•")
        conf = pen(f"[{f['confidence']}]", "grey")
        amt = ""
        if f["waste_mid"] > 0:
            amt = pen(f"  ~{_money(f['waste_mid'])}", "green")
        out.append(f"  {icon} {pen(f['title'], BOLD)} {conf}{amt}")
        out.append(f"     {pen(f['detail'], DIM)}")
        out.append(f"     {pen('→ ' + f['recommendation'], 'yellow')}")
        out.append("")
    rule()

    # ---- projection / budget ----
    proj = report["projection"]
    if proj.get("available"):
        out.append(pen("  PROJECTION", BOLD) + pen("  (estimate from 7-day run-rate)", DIM))
        out.append(
            f"  run-rate {_money(proj['daily_run_rate'])}/day · "
            f"MTD {_money(proj['month_to_date'])} · "
            f"month est. {pen(_money(proj['projected_month']), BOLD, 'cyan')}"
        )
        if budget:
            tone = {"ok": "green", "warn": "yellow", "over": "red"}[budget["state"]]
            pct = pen(f"{budget['pct_projected']*100:.0f}%", BOLD, tone)
            out.append(
                f"  budget {_money(budget['budget'])} · "
                f"projected {pct} used · "
                f"headroom {_money(budget['headroom'])}"
            )
        rule()

    if t.get("unpriced_models"):
        out.append(pen(f"  ⚠ {len(t['unpriced_models'])} unpriced model(s); spend understated.", "red"))
    out.append(pen("  computed locally · see docs/METHODOLOGY.md for every formula", DIM))
    out.append("")
    return "\n".join(out)
