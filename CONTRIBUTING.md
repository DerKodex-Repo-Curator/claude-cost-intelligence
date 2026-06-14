# Contributing

Thanks for helping make LLM spend less of a black box.

## Principles

1. **Zero runtime dependencies.** The library uses only the Python standard
   library. Dev tooling (pytest) is fine; runtime imports of third-party
   packages are not.
2. **Never fake a number.** Exact figures must be exact. Estimates must be
   labelled `estimated` and presented as a band. New detectors must document
   their formula and thresholds in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).
3. **Local-first.** No network calls, no telemetry, ever.
4. **Deterministic.** Same input → same output. Keep wall-clock dependence out of
   the analytics (pass `now` explicitly where time matters).

## Dev setup

```bash
python -m pip install -e ".[dev]"
python -m cci selftest      # 49-check built-in battery
python -m pytest -q         # full pytest suite
```

## Regenerating the demo assets

```bash
python -m cci sample --out examples/sample-usage.jsonl
python -m cci dashboard --path examples/sample-usage.jsonl --out cci-dashboard.html
# screenshots (Windows + Edge):
pwsh -File scripts/screenshot.ps1 -Html cci-dashboard.html
# headless JSON validation (any OS with Node):
node scripts/validate_dashboard.js cci-dashboard.html
```

## Adding a waste detector

1. Add a `_my_detector(events, an)` function in `cci/waste.py` returning a
   `Finding` (or `None` when the pattern is absent).
2. Register it in `detect()`.
3. Set `confidence` honestly and provide a `waste_low/mid/high` band.
4. Document the formula + thresholds in `docs/METHODOLOGY.md`.
5. Add a test in `tests/test_waste.py`.

## Before opening a PR

- `cci selftest` passes
- `pytest -q` passes
- New estimates are labelled and documented

PRs that add precision where there is none, or that phone home, will be declined.
