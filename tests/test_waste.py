from datetime import datetime, timezone

from cci.analytics import analyze
from cci.insights import build_report
from cci.normalize import collect
from cci.sampledata import generate
from cci.waste import detect


def setup_module(_m):
    global EVENTS, REPORT
    EVENTS = collect(generate(seed=7))
    REPORT = build_report(EVENTS, now=datetime(2026, 6, 14, 12, tzinfo=timezone.utc))


def _ids():
    return {f["id"] for f in REPORT["waste"]["findings"]}


def test_expected_detectors_fire_on_sample():
    ids = _ids()
    for expected in ("duplicate_prompts", "model_overprovisioning", "context_bloat", "concentration"):
        assert expected in ids, f"missing {expected}"


def test_recoverable_within_bounds():
    w = REPORT["waste"]
    assert 0 < w["recoverable_mid"] < REPORT["totals"]["cost"]
    assert w["recoverable_low"] <= w["recoverable_mid"] <= w["recoverable_high"]


def test_every_finding_band_ordered_and_labelled():
    for f in REPORT["waste"]["findings"]:
        assert f["waste_low"] <= f["waste_mid"] <= f["waste_high"] + 1e-9
        assert f["confidence"] in {"measured", "estimated", "n/a"}
        assert f["kind"] in {"savings", "attention", "data"}


def test_duplicate_detection_is_within_session():
    # the sample's retry loop sends one prompt 6x in a single session => 5 repeats
    dup = next(f for f in REPORT["waste"]["findings"] if f["id"] == "duplicate_prompts")
    assert dup["metrics"]["avoidable_requests"] >= 5
    # but it must NOT explode from canned prompts reused across many sessions
    assert dup["metrics"]["avoidable_requests"] < 30


def test_no_findings_on_empty_input():
    an = analyze([])
    w = detect([], an)
    assert w.findings == []
    assert w.recoverable_mid == 0.0
