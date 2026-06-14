import math

from cci.analytics import analyze
from cci.normalize import collect
from cci.sampledata import generate


def setup_module(_m):
    global EVENTS, AN
    EVENTS = collect(generate(seed=7))
    AN = analyze(EVENTS)


def test_buckets_sum_to_total():
    assert math.isclose(sum(b["cost"] for b in AN.by_model), AN.totals["cost"], abs_tol=1e-4)
    assert math.isclose(sum(b["cost"] for b in AN.by_project), AN.totals["cost"], abs_tol=1e-4)


def test_session_count_matches():
    assert AN.totals["sessions"] == len(AN.sessions)
    assert AN.totals["cost"] > 0


def test_pareto_monotone_and_bounded():
    rows = AN.pareto["rows"]
    for a, b in zip(rows, rows[1:]):
        assert a["cum_share"] <= b["cum_share"] + 1e-9
    assert rows[-1]["cum_share"] <= 1.0 + 1e-6
    assert 0 < AN.pareto["top1_share"] <= 1.0


def test_projection_fields_present():
    p = AN.projection
    assert p["available"] is True
    for k in ("daily_run_rate", "month_to_date", "projected_month", "days_remaining"):
        assert k in p


def test_sessions_sorted_by_cost_desc():
    costs = [s["cost"] for s in AN.sessions]
    assert costs == sorted(costs, reverse=True)


def test_meta_span_positive():
    assert AN.meta["span_days"] >= 1
    assert AN.meta["start"] and AN.meta["end"]
