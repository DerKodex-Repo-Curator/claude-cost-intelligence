"""Command-line interface for Claude Cost Intelligence.

Subcommands::

    cci report       # terminal cost intelligence report (default)
    cci dashboard    # generate a self-contained HTML dashboard
    cci sample       # write deterministic synthetic usage data
    cci budget       # budget status / projection
    cci json         # dump the raw report object as JSON
    cci selftest     # run the built-in test battery (no pytest needed)

Global filters: --path, --since, --until, --project, --model, --config, --pricing
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config as cfgmod, pricing
from .ingest import IngestStats, default_logs_dir, read_records
from .insights import build_report
from .normalize import Event, collect


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _filter(events: list[Event], args) -> list[Event]:
    since, until = _parse_date(args.since), _parse_date(args.until)
    proj = (args.project or "").lower()
    model = (args.model or "").lower()
    out = []
    for e in events:
        if since and e.ts and e.ts < since:
            continue
        if until and e.ts and e.ts > until:
            continue
        if proj and proj not in e.project.lower():
            continue
        if model and e.kind == "assistant" and model not in (e.model or "").lower():
            continue
        out.append(e)
    return out


def load_report(args, cfg: dict):
    if cfg.get("pricing"):
        pricing.merge_overrides(cfg["pricing"])
    if getattr(args, "pricing", None):
        try:
            pricing.merge_overrides(json.loads(Path(args.pricing).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            print(f"warning: could not load --pricing: {exc}", file=sys.stderr)
    root = Path(args.path) if args.path else default_logs_dir()
    stats = IngestStats()
    events = collect(read_records(root, stats))
    events = _filter(events, args)
    report = build_report(events)
    report["_ingest"] = {"files": stats.files, "lines": stats.lines, "parsed": stats.parsed, "skipped": stats.skipped}
    return report, stats, root


def cmd_report(args, cfg):
    from .report import render
    report, stats, root = load_report(args, cfg)
    if stats.parsed == 0:
        print(f"No usage data found under {root}.\n"
              f"Try:  cci sample  &&  cci report --path examples/sample-usage.jsonl", file=sys.stderr)
        return 1
    budget = cfgmod.budget_status(cfg, report["projection"])
    print(render(report, budget=budget))
    return 0


def cmd_dashboard(args, cfg):
    from .dashboard import render
    report, stats, root = load_report(args, cfg)
    if stats.parsed == 0:
        print(f"No usage data found under {root}.", file=sys.stderr)
        return 1
    budget = cfgmod.budget_status(cfg, report["projection"])
    out = Path(args.out)
    out.write_text(render(report, budget=budget), encoding="utf-8")
    print(f"Dashboard written: {out}  ({out.stat().st_size//1024} KB, {stats.parsed} events)")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_sample(args, cfg):
    from .sampledata import write
    out = Path(args.out)
    n = write(out, seed=args.seed)
    print(f"Wrote {n} synthetic records to {out}")
    print(f"Try:  cci dashboard --path {out} --open")
    return 0


def cmd_budget(args, cfg):
    report, stats, root = load_report(args, cfg)
    if stats.parsed == 0:
        print(f"No usage data found under {root}.", file=sys.stderr)
        return 1
    if args.set is not None:
        cfg["monthly_budget"] = float(args.set)
    budget = cfgmod.budget_status(cfg, report["projection"])
    if not budget:
        print("No budget set. Use --set <USD> or add monthly_budget to cci.config.json.")
        print(json.dumps(report["projection"], indent=2))
        return 0
    print(json.dumps(budget, indent=2))
    return 0 if budget["state"] != "over" else 2


def cmd_json(args, cfg):
    report, stats, root = load_report(args, cfg)
    report.pop("_ingest", None) if args.compact else None
    print(json.dumps(report, indent=None if args.compact else 2))
    return 0


def cmd_selftest(args, cfg):
    from .selftest import run
    return run(verbose=not args.quiet)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cci", description="Claude Cost Intelligence — local LLM spend intelligence.")
    p.add_argument("--version", action="version", version=f"cci {__version__}")

    def add_common(sp):
        sp.add_argument("--path", help="JSONL file or directory (default: ~/.claude/projects)")
        sp.add_argument("--since", help="only events on/after this date (YYYY-MM-DD)")
        sp.add_argument("--until", help="only events on/before this date (YYYY-MM-DD)")
        sp.add_argument("--project", help="filter by project substring")
        sp.add_argument("--model", help="filter by model substring")
        sp.add_argument("--config", help="path to a cci.config.json")
        sp.add_argument("--pricing", help="path to a pricing-override JSON")

    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("report", help="terminal cost report (default)")
    add_common(r); r.set_defaults(func=cmd_report)

    d = sub.add_parser("dashboard", help="generate self-contained HTML dashboard")
    add_common(d)
    d.add_argument("--out", default="cci-dashboard.html", help="output HTML path")
    d.add_argument("--open", action="store_true", help="open in browser when done")
    d.set_defaults(func=cmd_dashboard)

    s = sub.add_parser("sample", help="write deterministic synthetic usage data")
    s.add_argument("--out", default="examples/sample-usage.jsonl")
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(func=cmd_sample)

    b = sub.add_parser("budget", help="budget status / projection")
    add_common(b)
    b.add_argument("--set", help="set monthly budget (USD) for this run")
    b.set_defaults(func=cmd_budget)

    j = sub.add_parser("json", help="dump the report object as JSON")
    add_common(j)
    j.add_argument("--compact", action="store_true")
    j.set_defaults(func=cmd_json)

    t = sub.add_parser("selftest", help="run built-in tests (no pytest needed)")
    t.add_argument("--quiet", action="store_true")
    t.set_defaults(func=cmd_selftest)
    return p


KNOWN = {"report", "dashboard", "sample", "budget", "json", "selftest"}


def main(argv=None) -> int:
    # the report uses box-drawing / arrow glyphs; make sure Windows consoles
    # (cp1252 by default) don't choke on them.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    # default to `report` when no subcommand is named (so `cci --path x` works)
    if not argv or (argv[0] not in KNOWN and argv[0] not in ("-h", "--help", "--version")):
        argv = ["report", *argv]
    args = parser.parse_args(argv)
    cfg = cfgmod.load(getattr(args, "config", None))
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
