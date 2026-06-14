"""Waste detection + savings estimation — the "intelligence" in CCI.

Each detector turns a measurable pattern in the data into a :class:`Finding`
with a dollar band. We are deliberately honest about confidence:

* ``confidence="measured"`` — the pattern is exact (e.g. identical prompt sent
  N times). The avoidable-cost figure is still an estimate of *behaviour*, but
  the underlying signal is not modelled.
* ``confidence="estimated"`` — both detection and savings use heuristics and a
  documented reduction range. Always shown as a low–high band, never a single
  authoritative number.

No detector ever invents data. If a pattern is not present, it emits nothing.
See ``docs/METHODOLOGY.md`` for the full derivation of every formula.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import pricing
from .analytics import Analysis
from .normalize import Event

# Tunable thresholds (documented in METHODOLOGY.md). Kept here so they are
# auditable and overridable rather than scattered magic numbers.
DUP_MIN_OCCURRENCES = 3        # a prompt must appear >=3x to count as a pattern
DUP_MIN_PROMPT_LEN = 40        # ignore trivial "continue"/"yes" repeats
OVERUSE_OPUS_OUTPUT = 200      # opus turn with < this output = candidate downgrade
OVERUSE_SONNET_OUTPUT = 150    # sonnet turn with < this output = candidate downgrade
OVERUSE_LOW, OVERUSE_HIGH = 0.30, 0.80   # share of delta realistically recoverable
BLOAT_MIN_REQUESTS = 10
BLOAT_AVG_CONTEXT_TOK = 80_000   # avg carried context/turn above this = bloat
BLOAT_LOW, BLOAT_HIGH = 0.15, 0.30   # context cost reducible via /compact
CACHE_MIN_REQUESTS = 6
CACHE_MAX_HIT_RATIO = 0.35
CACHE_MIN_INPUT_TOK = 200_000
CACHE_LOW, CACHE_HIGH = 0.25, 0.75


@dataclass
class Finding:
    id: str
    title: str
    kind: str            # "savings" | "attention" | "data"
    confidence: str      # "measured" | "estimated" | "n/a"
    detail: str
    recommendation: str
    waste_low: float = 0.0
    waste_mid: float = 0.0
    waste_high: float = 0.0
    metrics: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "confidence": self.confidence,
            "detail": self.detail,
            "recommendation": self.recommendation,
            "waste_low": round(self.waste_low, 4),
            "waste_mid": round(self.waste_mid, 4),
            "waste_high": round(self.waste_high, 4),
            "metrics": self.metrics,
            "evidence": self.evidence,
        }


def _context_cost(e: Event) -> float:
    """USD spent on carried context (cache read + cache write) for one turn."""
    b = pricing.cost_breakdown(
        e.model, 0, 0, e.cache_write_5m, e.cache_write_1h, e.cache_read
    )
    return b["cache_write_5m"] + b["cache_write_1h"] + b["cache_read"]


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #

def _duplicate_prompts(events: list[Event], an: Analysis) -> Finding | None:
    # Group WITHIN a session: an identical prompt re-sent 3+ times in the same
    # session is a retry loop / re-ask — the strong, defensible waste signal.
    # The same prompt reused across separate sessions (a recurring task) is not
    # counted, so the metric never inflates on routine repeated work.
    groups: dict[tuple[str, str], list[Event]] = defaultdict(list)
    proj_of: dict[str, str] = {}
    for e in events:
        if e.kind == "user" and e.prompt_len >= DUP_MIN_PROMPT_LEN:
            groups[(e.session_id, e.prompt_hash)].append(e)
            proj_of[e.session_id] = e.project
    offenders = []
    avoidable_prompts = 0
    for (sid, _h), evs in groups.items():
        if len(evs) >= DUP_MIN_OCCURRENCES:
            repeats = len(evs) - 1
            avoidable_prompts += repeats
            offenders.append({
                "session_id": sid, "project": proj_of.get(sid, ""),
                "occurrences": len(evs), "repeats": repeats,
            })
    if not offenders:
        return None
    avg = an.totals["avg_cost_per_request"]
    mid = avoidable_prompts * avg
    offenders.sort(key=lambda o: o["repeats"], reverse=True)
    return Finding(
        id="duplicate_prompts",
        title="Duplicate prompts re-sent",
        kind="savings",
        confidence="measured",
        detail=(
            f"{len(offenders)} session(s) re-sent an identical prompt 3+ times, "
            f"causing ~{avoidable_prompts} avoidable request(s)."
        ),
        recommendation=(
            "Cache or memoize answers to repeated prompts; if a loop/retry is "
            "re-issuing identical requests, add a guard. Each avoided repeat "
            f"saves ~${avg:.4f} (avg request cost)."
        ),
        waste_low=avoidable_prompts * avg * 0.6,
        waste_mid=mid,
        waste_high=avoidable_prompts * avg * 1.4,
        metrics={"avoidable_requests": avoidable_prompts, "patterns": len(offenders)},
        evidence=offenders[:8],
    )


def _model_overprovisioning(events: list[Event]) -> Finding | None:
    delta_by_model: dict[str, float] = defaultdict(float)
    count_by_model: dict[str, int] = defaultdict(int)
    total_delta = 0.0
    turns = 0
    for e in events:
        if e.kind != "assistant" or not e.priced:
            continue
        p = pricing.resolve(e.model)
        if p.cheaper is None:
            continue
        threshold = OVERUSE_OPUS_OUTPUT if p.tier >= 3 else OVERUSE_SONNET_OUTPUT
        if e.output_tokens >= threshold:
            continue
        cheap = pricing._TABLE[p.cheaper]
        cur = e.cost
        # same tokens, billed at the cheaper model's rates
        alt_cost = (
            e.input_tokens * cheap.input
            + e.output_tokens * cheap.output
            + e.cache_write_5m * cheap.input * pricing.CACHE_WRITE_5M_MULT
            + e.cache_write_1h * cheap.input * pricing.CACHE_WRITE_1H_MULT
            + e.cache_read * cheap.input * pricing.CACHE_READ_MULT
        ) / 1_000_000.0
        delta = cur - alt_cost
        if delta <= 0:
            continue
        delta_by_model[p.display] += delta
        count_by_model[p.display] += 1
        total_delta += delta
        turns += 1
    if turns == 0 or total_delta <= 0:
        return None
    ev = sorted(
        ({"model": m, "turns": count_by_model[m], "delta": round(d, 4)} for m, d in delta_by_model.items()),
        key=lambda x: x["delta"],
        reverse=True,
    )
    return Finding(
        id="model_overprovisioning",
        title="Premium model on simple tasks",
        kind="savings",
        confidence="estimated",
        detail=(
            f"{turns} short-output turn(s) ran on a premium model. Routing the "
            "downgradeable share to the next-cheaper tier recovers most of the "
            "price delta."
        ),
        recommendation=(
            "Add model routing: send short / low-complexity turns to a cheaper "
            "tier (Haiku/Sonnet) and reserve premium models for hard tasks."
        ),
        waste_low=total_delta * OVERUSE_LOW,
        waste_mid=total_delta * (OVERUSE_LOW + OVERUSE_HIGH) / 2,
        waste_high=total_delta * OVERUSE_HIGH,
        metrics={"candidate_turns": turns, "full_price_delta": round(total_delta, 4)},
        evidence=ev[:6],
    )


def _context_bloat(events: list[Event], an: Analysis) -> Finding | None:
    ctx_cost: dict[str, float] = defaultdict(float)
    ctx_tok: dict[str, int] = defaultdict(int)
    reqs: dict[str, int] = defaultdict(int)
    proj: dict[str, str] = {}
    for e in events:
        if e.kind != "assistant":
            continue
        ctx_cost[e.session_id] += _context_cost(e)
        ctx_tok[e.session_id] += e.input_tokens + e.cache_read + e.cache_write_5m + e.cache_write_1h
        reqs[e.session_id] += 1
        proj[e.session_id] = e.project
    offenders = []
    total_ctx_cost = 0.0
    for sid, r in reqs.items():
        if r < BLOAT_MIN_REQUESTS:
            continue
        avg_ctx = ctx_tok[sid] / r
        if avg_ctx < BLOAT_AVG_CONTEXT_TOK:
            continue
        offenders.append({
            "session_id": sid,
            "project": proj[sid],
            "requests": r,
            "avg_context_tokens": int(avg_ctx),
            "context_cost": round(ctx_cost[sid], 4),
        })
        total_ctx_cost += ctx_cost[sid]
    if not offenders:
        return None
    offenders.sort(key=lambda o: o["context_cost"], reverse=True)
    return Finding(
        id="context_bloat",
        title="Oversized context windows",
        kind="savings",
        confidence="estimated",
        detail=(
            f"{len(offenders)} long session(s) carried >"
            f"{BLOAT_AVG_CONTEXT_TOK // 1000}k tokens of context per turn. "
            f"Context billing in these sessions totalled ${total_ctx_cost:.2f}."
        ),
        recommendation=(
            "Compact or summarize context periodically (/compact), prune stale "
            "files from the window, and start fresh sessions for unrelated work."
        ),
        waste_low=total_ctx_cost * BLOAT_LOW,
        waste_mid=total_ctx_cost * (BLOAT_LOW + BLOAT_HIGH) / 2,
        waste_high=total_ctx_cost * BLOAT_HIGH,
        metrics={"sessions": len(offenders), "context_cost": round(total_ctx_cost, 4)},
        evidence=offenders[:6],
    )


def _cache_inefficiency(events: list[Event]) -> Finding | None:
    agg: dict[str, dict] = defaultdict(lambda: {"in": 0, "cr": 0, "cw": 0, "req": 0, "model": "", "project": ""})
    for e in events:
        if e.kind != "assistant":
            continue
        a = agg[e.session_id]
        a["in"] += e.input_tokens
        a["cr"] += e.cache_read
        a["cw"] += e.cache_write_5m + e.cache_write_1h
        a["req"] += 1
        a["model"] = e.model or a["model"]
        a["project"] = e.project
    offenders, avoidable = [], 0.0
    for sid, a in agg.items():
        denom = a["in"] + a["cr"] + a["cw"]
        if a["req"] < CACHE_MIN_REQUESTS or denom == 0:
            continue
        hit = a["cr"] / denom
        if hit >= CACHE_MAX_HIT_RATIO or a["in"] < CACHE_MIN_INPUT_TOK:
            continue
        # half the fresh input beyond the first turn could plausibly be cached;
        # caching it converts input price (1.0x) to cache-read (0.1x) -> 0.9x saved
        recoverable_tok = a["in"] * 0.5
        in_price = pricing.resolve(a["model"]).input
        save = recoverable_tok * in_price * 0.9 / 1e6
        avoidable += save
        offenders.append({
            "session_id": sid, "project": a["project"], "requests": a["req"],
            "hit_ratio": round(hit, 3), "input_tokens": a["in"],
        })
    if not offenders:
        return None
    offenders.sort(key=lambda o: o["input_tokens"], reverse=True)
    return Finding(
        id="cache_inefficiency",
        title="Low prompt-cache hit rate",
        kind="savings",
        confidence="estimated",
        detail=(
            f"{len(offenders)} session(s) re-sent large prompts with a cache hit "
            "ratio below 35%. Cached reads cost 10% of fresh input."
        ),
        recommendation=(
            "Enable prompt caching for stable prefixes (system prompt, large "
            "shared context) so repeated tokens bill at 0.1x instead of 1.0x."
        ),
        waste_low=avoidable * CACHE_LOW,
        waste_mid=avoidable * (CACHE_LOW + CACHE_HIGH) / 2,
        waste_high=avoidable * CACHE_HIGH,
        metrics={"sessions": len(offenders)},
        evidence=offenders[:6],
    )


def _concentration(an: Analysis) -> Finding | None:
    p = an.pareto
    if p["sessions_total"] < 4:
        return None
    n = p["sessions_to_half"]
    detail = (
        f"{n} of {p['sessions_total']} session(s) account for ~50% of spend; "
        f"the single most expensive session is {p['top1_share']*100:.0f}% of total."
    )
    return Finding(
        id="concentration",
        title="Spend concentrated in few sessions",
        kind="attention",
        confidence="measured",
        detail=detail,
        recommendation=(
            "Audit the top sessions first — fixing the few whales yields the "
            "biggest return. Open them in the Sessions view."
        ),
        metrics={
            "sessions_to_half": n,
            "top1_share": round(p["top1_share"], 4),
            "top5pct_share": round(p["top5pct_share"], 4),
        },
        evidence=p["rows"][:5],
    )


def _errors(events: list[Event]) -> Finding | None:
    bad = [e for e in events if e.kind == "assistant" and e.is_error]
    if not bad:
        return None
    cost = sum(e.cost for e in bad)
    if cost <= 0:
        return None
    return Finding(
        id="error_retry_waste",
        title="Spend on errored / truncated turns",
        kind="savings",
        confidence="measured",
        detail=f"{len(bad)} turn(s) ended in error or hit max_tokens, costing ${cost:.2f}.",
        recommendation=(
            "Investigate recurring errors and raise max_tokens only where needed; "
            "truncated outputs often get re-run, doubling cost."
        ),
        waste_low=cost * 0.5,
        waste_mid=cost,
        waste_high=cost,
        metrics={"errored_turns": len(bad)},
        evidence=[],
    )


def _unpriced(an: Analysis) -> Finding | None:
    models = an.totals.get("unpriced_models") or []
    if not models:
        return None
    return Finding(
        id="unpriced_usage",
        title="Usage from unpriced models",
        kind="data",
        confidence="n/a",
        detail=f"{len(models)} model id(s) have no price and are costed at $0: {', '.join(models)}.",
        recommendation=(
            "Add prices for these models via --pricing / config so their cost is "
            "included. Until then, totals understate true spend."
        ),
        metrics={"models": models},
        evidence=[],
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

@dataclass
class WasteReport:
    findings: list[dict]
    recoverable_low: float
    recoverable_mid: float
    recoverable_high: float
    recoverable_pct: float

    def as_dict(self) -> dict:
        return {
            "findings": self.findings,
            "recoverable_low": round(self.recoverable_low, 2),
            "recoverable_mid": round(self.recoverable_mid, 2),
            "recoverable_high": round(self.recoverable_high, 2),
            "recoverable_pct": round(self.recoverable_pct, 4),
        }


def detect(events: list[Event], an: Analysis) -> WasteReport:
    detectors = [
        _duplicate_prompts(events, an),
        _model_overprovisioning(events),
        _context_bloat(events, an),
        _cache_inefficiency(events),
        _errors(events),
        _concentration(an),
        _unpriced(an),
    ]
    findings = [f for f in detectors if f is not None]
    # savings findings first, by mid value desc; then attention; then data
    order = {"savings": 0, "attention": 1, "data": 2}
    findings.sort(key=lambda f: (order[f.kind], -f.waste_mid))

    low = sum(f.waste_low for f in findings)
    mid = sum(f.waste_mid for f in findings)
    high = sum(f.waste_high for f in findings)
    total = an.totals["cost"] or 1e-12
    return WasteReport(
        findings=[f.as_dict() for f in findings],
        recoverable_low=low,
        recoverable_mid=mid,
        recoverable_high=high,
        recoverable_pct=mid / total,
    )
