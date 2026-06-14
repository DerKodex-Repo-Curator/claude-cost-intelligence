"""Built-in test battery — ``cci selftest``.

Runs without pytest so CI (and users) can verify a checkout with only the
standard library. Returns 0 on success, 1 on any failure. The pytest files in
``tests/`` exercise the same logic with finer granularity.
"""

from __future__ import annotations

import json

from . import config as cfgmod, pricing
from .analytics import analyze
from .dashboard import render as dash_render
from .insights import build_report
from .normalize import collect
from .sampledata import generate

_checks = 0
_fails = 0


def _ok(cond, msg):
    global _checks, _fails
    _checks += 1
    if not cond:
        _fails += 1
        print(f"  FAIL: {msg}")


def _close(a, b, eps=1e-9):
    return abs(a - b) <= eps


def run(verbose: bool = True) -> int:
    global _checks, _fails
    _checks = _fails = 0

    # --- pricing: exact arithmetic ---
    _ok(_close(pricing.cost_of("claude-opus-4-8", input_tokens=1_000_000), 15.0), "opus input/MTok=15")
    _ok(_close(pricing.cost_of("claude-opus-4-8", output_tokens=1_000_000), 75.0), "opus output/MTok=75")
    _ok(_close(pricing.cost_of("claude-opus-4-8", cache_read=1_000_000), 1.5), "opus cache read=0.1x")
    _ok(_close(pricing.cost_of("claude-opus-4-8", cache_write_5m=1_000_000), 18.75), "opus cache write 5m=1.25x")
    _ok(_close(pricing.cost_of("claude-opus-4-8", cache_write_1h=1_000_000), 30.0), "opus cache write 1h=2x")
    _ok(_close(pricing.cost_of("claude-sonnet-4-6", input_tokens=1_000_000), 3.0), "sonnet input=3")
    _ok(_close(pricing.cost_of("claude-haiku-4-5", input_tokens=1_000_000), 1.0), "haiku4.5 input=1")

    # --- pricing: model resolution ---
    _ok(pricing.resolve("claude-opus-4-8").key == "opus", "resolve opus")
    _ok(pricing.resolve("claude-sonnet-4-6").key == "sonnet", "resolve sonnet")
    _ok(pricing.resolve("claude-haiku-4-5-20251001").key == "haiku", "resolve haiku4")
    _ok(pricing.resolve("claude-3-5-haiku-20241022").input == 0.80, "resolve 3.5 haiku=0.8")
    _ok(pricing.resolve("claude-3-haiku-20240307").input == 0.25, "resolve 3 haiku=0.25")
    _ok(not pricing.resolve("<synthetic>").priced, "synthetic unpriced")
    _ok(pricing.resolve("opus").cheaper == "sonnet", "opus cheaper=sonnet")

    # --- pricing: breakdown sums to total ---
    bd = pricing.cost_breakdown("claude-opus-4-8", 1000, 500, 200, 100, 4000)
    tot = pricing.cost_of("claude-opus-4-8", 1000, 500, 200, 100, 4000)
    _ok(_close(sum(bd.values()), tot), "breakdown sums to cost_of")

    # --- normalize + analytics on synthetic data ---
    records = generate(seed=7)
    events = collect(records)
    _ok(any(e.kind == "assistant" for e in events), "assistant events present")
    _ok(any(e.kind == "user" for e in events), "user events present")
    an = analyze(events)
    by_model_sum = sum(b["cost"] for b in an.by_model)
    _ok(_close(by_model_sum, an.totals["cost"], eps=1e-4), "by_model sums to total cost")
    by_proj_sum = sum(b["cost"] for b in an.by_project)
    _ok(_close(by_proj_sum, an.totals["cost"], eps=1e-4), "by_project sums to total cost")
    _ok(an.totals["sessions"] == len(an.sessions), "session count matches")
    _ok(an.totals["cost"] > 0, "total cost positive")

    # --- pareto: cumulative share monotone, ends ~1 ---
    rows = an.pareto["rows"]
    mono = all(rows[i]["cum_share"] <= rows[i + 1]["cum_share"] + 1e-9 for i in range(len(rows) - 1))
    _ok(mono, "pareto cumulative monotone")
    if rows:
        _ok(rows[-1]["cum_share"] <= 1.0 + 1e-6, "pareto ends <=1")

    # --- waste detection ---
    report = build_report(events)
    w = report["waste"]
    ids = {f["id"] for f in w["findings"]}
    _ok("duplicate_prompts" in ids, "detects duplicate prompts")
    _ok("model_overprovisioning" in ids, "detects model overprovisioning")
    _ok("context_bloat" in ids, "detects context bloat")
    _ok("concentration" in ids, "detects concentration")
    _ok(0 < w["recoverable_mid"] < report["totals"]["cost"], "recoverable in (0, total)")
    _ok(w["recoverable_low"] <= w["recoverable_mid"] <= w["recoverable_high"], "recoverable band ordered")
    for f in w["findings"]:
        _ok(f["waste_low"] <= f["waste_mid"] <= f["waste_high"] + 1e-9, f"finding band ordered: {f['id']}")
        _ok(f["confidence"] in {"measured", "estimated", "n/a"}, f"confidence labelled: {f['id']}")

    # --- determinism (given a fixed clock; generated_at is the only wall-clock field) ---
    from datetime import datetime, timezone
    fixed = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
    r1 = json.dumps(build_report(collect(generate(7)), now=fixed), sort_keys=True)
    r2 = json.dumps(build_report(collect(generate(7)), now=fixed), sort_keys=True)
    _ok(r1 == r2, "report deterministic for fixed seed + clock")

    # --- dashboard render is self-contained ---
    html = dash_render(report, budget=None)
    _ok("__DATA__" not in html, "dashboard placeholder replaced")
    _ok("Claude Cost Intelligence" in html, "dashboard has title")
    _ok("</script>" in html and html.count("<script") >= 2, "dashboard scripts intact")
    _ok(len(html) > 5000, "dashboard non-trivial size")

    # --- config / budget ---
    proj = report["projection"]
    if proj.get("available"):
        st = cfgmod.budget_status({"monthly_budget": proj["projected_month"] * 2, "warn_at": 0.8}, proj)
        _ok(st and st["state"] == "ok", "budget ok under half")
        st = cfgmod.budget_status({"monthly_budget": proj["projected_month"] * 0.5, "warn_at": 0.8}, proj)
        _ok(st and st["state"] == "over", "budget over when projection exceeds")

    # --- ingest robustness: malformed lines skipped ---
    from .ingest import IngestStats, read_records
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"type":"assistant","message":{"model":"claude-haiku-4-5","usage":{"output_tokens":10}}}\n')
        fh.write("not json at all\n")
        fh.write("\n")
        fh.write('{"broken":')
    st = IngestStats()
    got = list(read_records(__import__("pathlib").Path(path), st))
    os.unlink(path)
    _ok(len(got) == 1 and st.skipped == 2, "ingest skips malformed lines")

    if verbose:
        status = "ALLPASS" if _fails == 0 else f"{_fails} FAILED"
        print(f"cci selftest: {_checks - _fails}/{_checks} checks pass — {status}")
    return 0 if _fails == 0 else 1
