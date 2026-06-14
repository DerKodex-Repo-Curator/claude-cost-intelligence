"""Aggregation + analytics engine.

Turns a flat list of :class:`~cci.normalize.Event` into the structured rollups
the dashboard and report consume: totals, by-model, by-project, by-day,
per-session, Pareto concentration, and a (clearly labelled) spend projection.

All math here is deterministic and exact given the input events; the only
estimate is :func:`project_month`, which extrapolates a run-rate and is always
presented as an estimate.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .normalize import Event


def _tok_total(e: Event) -> int:
    return e.input_tokens + e.output_tokens + e.cache_write_5m + e.cache_write_1h + e.cache_read


@dataclass
class Bucket:
    """Generic spend/usage accumulator keyed by some dimension."""

    key: str
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0
    requests: int = 0
    sessions: set = field(default_factory=set)
    unpriced: bool = False

    def add(self, e: Event) -> None:
        self.cost += e.cost
        self.input_tokens += e.input_tokens
        self.output_tokens += e.output_tokens
        self.cache_write += e.cache_write_5m + e.cache_write_1h
        self.cache_read += e.cache_read
        self.requests += 1
        self.sessions.add(e.session_id)
        if not e.priced:
            self.unpriced = True

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_write + self.cache_read

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "cost": round(self.cost, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write": self.cache_write,
            "cache_read": self.cache_read,
            "tokens": self.tokens,
            "requests": self.requests,
            "sessions": len(self.sessions),
            "unpriced": self.unpriced,
        }


@dataclass
class SessionStat:
    session_id: str
    project: str
    cost: float = 0.0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    models: set = field(default_factory=set)
    start: datetime | None = None
    end: datetime | None = None
    prompts: int = 0
    errors: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_write

    @property
    def duration_min(self) -> float:
        if self.start and self.end:
            return max(0.0, (self.end - self.start).total_seconds() / 60.0)
        return 0.0

    @property
    def cache_hit_ratio(self) -> float:
        denom = self.input_tokens + self.cache_read + self.cache_write
        return (self.cache_read / denom) if denom else 0.0

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "project": self.project,
            "cost": round(self.cost, 6),
            "requests": self.requests,
            "prompts": self.prompts,
            "tokens": self.tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "models": sorted(self.models),
            "duration_min": round(self.duration_min, 1),
            "cache_hit_ratio": round(self.cache_hit_ratio, 4),
            "errors": self.errors,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
        }


def build_sessions(events: list[Event]) -> dict[str, SessionStat]:
    sessions: dict[str, SessionStat] = {}
    for e in events:
        s = sessions.get(e.session_id)
        if s is None:
            s = SessionStat(session_id=e.session_id, project=e.project)
            sessions[e.session_id] = s
        if e.ts:
            s.start = e.ts if s.start is None or e.ts < s.start else s.start
            s.end = e.ts if s.end is None or e.ts > s.end else s.end
        if e.kind == "user":
            s.prompts += 1
            continue
        s.cost += e.cost
        s.requests += 1
        s.input_tokens += e.input_tokens
        s.output_tokens += e.output_tokens
        s.cache_read += e.cache_read
        s.cache_write += e.cache_write_5m + e.cache_write_1h
        if e.model:
            s.models.add(e.model)
        if e.is_error:
            s.errors += 1
    return sessions


def _bucket_by(events: list[Event], keyfn) -> list[Bucket]:
    buckets: dict[str, Bucket] = {}
    for e in events:
        if e.kind != "assistant":
            continue
        k = keyfn(e)
        b = buckets.get(k)
        if b is None:
            b = Bucket(key=k)
            buckets[k] = b
        b.add(e)
    return sorted(buckets.values(), key=lambda b: b.cost, reverse=True)


def pareto(sessions: list[dict]) -> dict:
    """Concentration metrics: how few sessions drive how much spend."""
    ranked = sorted(sessions, key=lambda s: s["cost"], reverse=True)
    total = sum(s["cost"] for s in ranked) or 1e-12
    cum, rows = 0.0, []
    half_n = None
    for i, s in enumerate(ranked, 1):
        cum += s["cost"]
        share = cum / total
        rows.append({"rank": i, "session_id": s["session_id"], "cost": s["cost"], "cum_share": share})
        if half_n is None and share >= 0.5:
            half_n = i
    n = len(ranked)
    top = lambda frac: sum(s["cost"] for s in ranked[: max(1, round(n * frac))]) / total if n else 0.0
    return {
        "sessions_to_half": half_n or n,
        "sessions_total": n,
        "top1_share": (ranked[0]["cost"] / total) if ranked else 0.0,
        "top5pct_share": top(0.05),
        "top10pct_share": top(0.10),
        "rows": rows[:50],
    }


def by_day(events: list[Event]) -> list[dict]:
    days: dict[str, dict] = {}
    for e in events:
        if e.kind != "assistant" or not e.ts:
            continue
        d = e.ts.date().isoformat()
        row = days.setdefault(d, {"day": d, "cost": 0.0, "tokens": 0, "requests": 0})
        row["cost"] += e.cost
        row["tokens"] += _tok_total(e)
        row["requests"] += 1
    return [
        {**r, "cost": round(r["cost"], 6)}
        for r in sorted(days.values(), key=lambda r: r["day"])
    ]


def project_month(daily: list[dict], now: datetime | None = None) -> dict:
    """Estimate end-of-month spend from a trailing 7-day run-rate.

    Clearly an ESTIMATE. Returns the run-rate, days remaining, projected total
    for the current calendar month, and the window used.
    """
    if not daily:
        return {"available": False}
    now = now or datetime.now(timezone.utc)
    recent = daily[-7:]
    rate = sum(d["cost"] for d in recent) / len(recent)
    # month-to-date for the current calendar month
    ym = now.strftime("%Y-%m")
    mtd = sum(d["cost"] for d in daily if d["day"].startswith(ym))
    # days remaining in month
    if now.month == 12:
        first_next = now.replace(year=now.year + 1, month=1, day=1)
    else:
        first_next = now.replace(month=now.month + 1, day=1)
    days_left = (first_next.date() - now.date()).days
    return {
        "available": True,
        "daily_run_rate": round(rate, 4),
        "window_days": len(recent),
        "month_to_date": round(mtd, 4),
        "days_remaining": days_left,
        "projected_month": round(mtd + rate * days_left, 2),
    }


@dataclass
class Analysis:
    totals: dict
    by_model: list[dict]
    by_project: list[dict]
    daily: list[dict]
    sessions: list[dict]
    pareto: dict
    projection: dict
    meta: dict


def analyze(events: list[Event], now: datetime | None = None) -> Analysis:
    assistant = [e for e in events if e.kind == "assistant"]
    sess_map = build_sessions(events)
    sessions = sorted((s.as_dict() for s in sess_map.values()), key=lambda s: s["cost"], reverse=True)

    total_cost = sum(e.cost for e in assistant)
    in_tok = sum(e.input_tokens for e in assistant)
    out_tok = sum(e.output_tokens for e in assistant)
    cw_tok = sum(e.cache_write_5m + e.cache_write_1h for e in assistant)
    cr_tok = sum(e.cache_read for e in assistant)
    prompts = sum(1 for e in events if e.kind == "user")
    ts_vals = [e.ts for e in events if e.ts]
    unpriced_cost_models = sorted({e.model for e in assistant if not e.priced})

    costs = sorted((s["cost"] for s in sessions), reverse=True)
    totals = {
        "cost": round(total_cost, 4),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_write_tokens": cw_tok,
        "cache_read_tokens": cr_tok,
        "tokens": in_tok + out_tok + cw_tok + cr_tok,
        "requests": len(assistant),
        "prompts": prompts,
        "sessions": len(sessions),
        "projects": len({e.project for e in assistant}),
        "models": len({e.model for e in assistant}),
        "errors": sum(1 for e in assistant if e.is_error),
        "avg_cost_per_session": round(total_cost / len(sessions), 4) if sessions else 0.0,
        "median_session_cost": round(statistics.median(costs), 6) if costs else 0.0,
        "avg_cost_per_request": round(total_cost / len(assistant), 6) if assistant else 0.0,
        "cache_read_share": round(cr_tok / (in_tok + cr_tok + cw_tok), 4) if (in_tok + cr_tok + cw_tok) else 0.0,
        "unpriced_models": unpriced_cost_models,
    }

    daily = by_day(events)
    meta = {
        "start": min(ts_vals).isoformat() if ts_vals else None,
        "end": max(ts_vals).isoformat() if ts_vals else None,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "span_days": (max(ts_vals).date() - min(ts_vals).date()).days + 1 if ts_vals else 0,
    }

    return Analysis(
        totals=totals,
        by_model=[b.as_dict() for b in _bucket_by(assistant, lambda e: e.model or "unknown")],
        by_project=[b.as_dict() for b in _bucket_by(assistant, lambda e: e.project)],
        daily=daily,
        sessions=sessions,
        pareto=pareto(sessions),
        projection=project_month(daily, now),
        meta=meta,
    )
