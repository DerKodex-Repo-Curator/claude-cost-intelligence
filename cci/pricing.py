"""Deterministic, transparent pricing for Claude / Anthropic models.

Every dollar figure CCI reports is computed here. No network calls, no hidden
fudge factors. Prices are USD per 1,000,000 tokens (per MTok) and match
Anthropic's published list prices. Cache multipliers follow Anthropic's policy:

    cache write (5-minute TTL) = 1.25x base input price
    cache write (1-hour TTL)   = 2.00x base input price
    cache read                 = 0.10x base input price

If a model cannot be priced, its cost is 0.0 and it is flagged as ``unpriced``
so the report can warn you that some usage is not costed (never silently
swallowed).
"""

from __future__ import annotations

from dataclasses import dataclass

# Cache multipliers relative to base input price (Anthropic policy).
CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.00
CACHE_READ_MULT = 0.10


@dataclass(frozen=True)
class Price:
    """List price for one model, USD per MTok."""

    key: str            # canonical short key, e.g. "opus"
    display: str        # human label, e.g. "Claude Opus"
    input: float        # $/MTok input
    output: float       # $/MTok output
    tier: int           # 1 cheap .. 3 premium
    cheaper: str | None  # canonical key of next-cheaper tier, for overuse logic
    priced: bool = True


# Canonical list prices (USD / MTok). Sourced from Anthropic public pricing.
# Opus 4.x / 3-opus: 15 / 75 | Sonnet (3.5 & 4.x): 3 / 15 | Haiku 4.x: 1 / 5
# 3.5 Haiku: 0.80 / 4 | 3 Haiku: 0.25 / 1.25
_TABLE = {
    "opus": Price("opus", "Claude Opus", 15.0, 75.0, tier=3, cheaper="sonnet"),
    "sonnet": Price("sonnet", "Claude Sonnet", 3.0, 15.0, tier=2, cheaper="haiku"),
    "haiku": Price("haiku", "Claude Haiku", 1.0, 5.0, tier=1, cheaper=None),
    "haiku-3-5": Price("haiku-3-5", "Claude 3.5 Haiku", 0.80, 4.0, tier=1, cheaper=None),
    "haiku-3": Price("haiku-3", "Claude 3 Haiku", 0.25, 1.25, tier=1, cheaper=None),
}

_UNPRICED = Price("unpriced", "Unpriced/unknown", 0.0, 0.0, tier=0, cheaper=None, priced=False)


def resolve(model: str) -> Price:
    """Map a raw model id (e.g. ``claude-opus-4-8``) to a :class:`Price`."""
    if not model:
        return _UNPRICED
    m = model.lower()
    if "opus" in m:
        return _TABLE["opus"]
    if "sonnet" in m:
        return _TABLE["sonnet"]
    if "haiku" in m:
        if "3-5" in m or "3.5" in m:
            return _TABLE["haiku-3-5"]
        # "claude-3-haiku-..." but not 3-5 -> legacy cheap Haiku
        if "-3-" in m or m.endswith("-3") or "claude-3-haiku" in m:
            return _TABLE["haiku-3"]
        return _TABLE["haiku"]
    return _UNPRICED


def merge_overrides(overrides: dict | None) -> None:
    """Apply user pricing overrides in-place.

    ``overrides`` is ``{canonical_key: {"input": x, "output": y}}``. Lets teams
    encode negotiated / enterprise pricing without forking the code.
    """
    if not overrides:
        return
    for key, vals in overrides.items():
        base = _TABLE.get(key)
        if base is None:
            continue
        _TABLE[key] = Price(
            key=base.key,
            display=base.display,
            input=float(vals.get("input", base.input)),
            output=float(vals.get("output", base.output)),
            tier=base.tier,
            cheaper=base.cheaper,
            priced=True,
        )


def cost_of(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
    cache_read: int = 0,
) -> float:
    """Return total USD cost of a single request's token usage.

    Cache-write tokens are billed at the 5-minute or 1-hour multiplier; cache
    reads at 0.10x; fresh input and output at list price. Deterministic.
    """
    p = resolve(model)
    return (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_write_5m * p.input * CACHE_WRITE_5M_MULT
        + cache_write_1h * p.input * CACHE_WRITE_1H_MULT
        + cache_read * p.input * CACHE_READ_MULT
    ) / 1_000_000.0


def cost_breakdown(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
    cache_read: int = 0,
) -> dict:
    """Per-component cost breakdown (used by the trust/methodology view)."""
    p = resolve(model)
    return {
        "input": input_tokens * p.input / 1e6,
        "output": output_tokens * p.output / 1e6,
        "cache_write_5m": cache_write_5m * p.input * CACHE_WRITE_5M_MULT / 1e6,
        "cache_write_1h": cache_write_1h * p.input * CACHE_WRITE_1H_MULT / 1e6,
        "cache_read": cache_read * p.input * CACHE_READ_MULT / 1e6,
    }


def all_prices() -> list[Price]:
    """Distinct priced models (for the pricing table in the dashboard)."""
    seen, out = set(), []
    for p in _TABLE.values():
        if p.key not in seen:
            seen.add(p.key)
            out.append(p)
    return out
