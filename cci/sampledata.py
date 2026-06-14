"""Deterministic synthetic usage generator.

Produces a JSONL file in the exact shape Claude Code writes, so the dashboard
and report can be demoed with zero real data. The synthetic month deliberately
contains realistic waste patterns (a whale session, a retry loop, premium-model
overuse, a low-cache session) so the optimization view has something to find.

Deterministic: same seed -> byte-identical output. No globals are mutated.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"

PROJECTS = ["acme-api", "web-app", "data-pipeline", "experiments"]
PROMPTS = [
    "Refactor the auth middleware to support token refresh and rotation.",
    "Why is the checkout endpoint returning 500 under load?",
    "Write unit tests for the pricing module covering cache tiers.",
    "Summarize the last migration and its rollback plan.",
    "Optimize this SQL query, it scans the whole orders table.",
    "Add retry with backoff to the webhook dispatcher.",
]


def _hexid(rng: random.Random, n: int = 32) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _ts(base: datetime, day: int, minute: int) -> str:
    return (base + timedelta(days=day, minutes=minute)).isoformat().replace("+00:00", "Z")


def _assistant(rng, sid, project, model, ts, inp, out, cw5, cr, stop="end_turn", cw1h=0):
    return {
        "type": "assistant",
        "sessionId": sid,
        "cwd": f"/home/dev/{project}",
        "timestamp": ts,
        "requestId": "req_" + _hexid(rng, 20),
        "uuid": _hexid(rng, 32),
        "version": "2.1.158",
        "message": {
            "model": model,
            "role": "assistant",
            "stop_reason": stop,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cw5 + cw1h,
                "cache_read_input_tokens": cr,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": cw5,
                    "ephemeral_1h_input_tokens": cw1h,
                },
            },
        },
    }


def _user(rng, sid, project, ts, text):
    return {
        "type": "user",
        "sessionId": sid,
        "cwd": f"/home/dev/{project}",
        "timestamp": ts,
        "uuid": _hexid(rng, 32),
        "message": {"role": "user", "content": text},
    }


def generate(seed: int = 7, days: int = 30) -> list[dict]:
    rng = random.Random(seed)
    base = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    recs: list[dict] = []

    def new_sid():
        return _hexid(rng, 32)

    # 1) WHALE: long expensive Opus session on data-pipeline (concentration + bloat)
    sid = new_sid()
    recs.append(_user(rng, sid, "data-pipeline", _ts(base, 8, 0), PROMPTS[4]))
    for i in range(52):
        cr = rng.randint(110_000, 160_000)          # huge carried context
        cw5 = 28_000 if i % 6 == 0 else 0
        recs.append(_assistant(rng, sid, "data-pipeline", OPUS,
                               _ts(base, 8, 2 + i * 3),
                               inp=rng.randint(1500, 3500), out=rng.randint(1800, 3200),
                               cw5=cw5, cr=cr))

    # 2) RETRY LOOP: identical prompt sent 6x (duplicate_prompts)
    sid = new_sid()
    dup = "Generate the weekly metrics report from the analytics table and email it."
    for i in range(6):
        recs.append(_user(rng, sid, "experiments", _ts(base, 12, i * 4), dup))
        recs.append(_assistant(rng, sid, "experiments", SONNET, _ts(base, 12, i * 4 + 1),
                               inp=rng.randint(800, 1500), out=rng.randint(400, 900),
                               cw5=0, cr=rng.randint(8000, 20000)))

    # 3) OVERPROVISIONING: many tiny Opus turns on web-app (premium for simple)
    for d in range(5):
        sid = new_sid()
        recs.append(_user(rng, sid, "web-app", _ts(base, 15 + d, 0), rng.choice(PROMPTS)))
        for i in range(7):
            recs.append(_assistant(rng, sid, "web-app", OPUS, _ts(base, 15 + d, 1 + i * 2),
                                   inp=rng.randint(400, 1200), out=rng.randint(40, 160),
                                   cw5=0, cr=rng.randint(4000, 12000)))

    # 4) LOW-CACHE: big fresh input, poor cache reuse (cache_inefficiency)
    sid = new_sid()
    for i in range(9):
        recs.append(_assistant(rng, sid, "acme-api", SONNET, _ts(base, 20, i * 6),
                               inp=rng.randint(30_000, 55_000), out=rng.randint(600, 1400),
                               cw5=0, cr=rng.randint(0, 4000)))

    # 5) NORMAL background traffic across the month
    for d in range(days):
        n = rng.randint(1, 4)
        for _ in range(n):
            sid = new_sid()
            project = rng.choice(PROJECTS)
            model = rng.choices([HAIKU, SONNET, OPUS], weights=[5, 4, 1])[0]
            turns = rng.randint(2, 9)
            recs.append(_user(rng, sid, project, _ts(base, d, 0), rng.choice(PROMPTS)))
            for i in range(turns):
                stop = "max_tokens" if rng.random() < 0.02 else "end_turn"
                recs.append(_assistant(rng, sid, project, model, _ts(base, d, 1 + i * 5),
                                       inp=rng.randint(600, 4000), out=rng.randint(300, 2200),
                                       cw5=rng.choice([0, 0, 6000]),
                                       cr=rng.randint(5000, 60000), stop=stop))

    recs.sort(key=lambda r: r["timestamp"])
    return recs


def write(path: Path, seed: int = 7) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    recs = generate(seed)
    with path.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    return len(recs)
