# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.0] — 2026-06-14

First public release.

### Added
- **Exact cost engine** (`cci/pricing.py`): cache-tier-aware Anthropic list pricing, deterministic, with per-model overrides and unpriced-model flagging.
- **Ingestion** of Claude Code JSONL logs — streaming, malformed-line tolerant, local-only.
- **Analytics**: totals, by-model, by-project, by-day, per-session stats, Pareto concentration, and a labelled month projection.
- **Waste detection + savings estimation**: duplicate prompts, oversized context, premium-model overuse, low cache-hit rate, errored/truncated turns, concentration, unpriced usage — each with a confidence label and a low–high dollar band.
- **Terminal report** with ANSI bars (honors `NO_COLOR`).
- **Self-contained HTML dashboard** — six views (Overview, Models, Sessions, Projects, Optimization, Budget), inline SVG/CSS charts, zero CDN/network.
- **CLI**: `report`, `dashboard`, `sample`, `budget`, `json`, `selftest`; global `--path/--since/--until/--project/--model/--config/--pricing` filters.
- **Budget + projection** with warn/over states and config loader.
- **Deterministic synthetic data generator** (`cci sample`) with built-in waste patterns for instant demos.
- **Tests**: built-in `cci selftest` (49 checks, no pytest required) + a pytest suite; CI across Linux/macOS/Windows on Python 3.9/3.11/3.12 plus a headless dashboard-validation job.
- **Docs**: full [METHODOLOGY.md](docs/METHODOLOGY.md) documenting every formula, threshold, and what is exact vs estimated.
