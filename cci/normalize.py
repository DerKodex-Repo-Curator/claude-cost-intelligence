"""Normalization: raw JSONL records -> typed, costed events.

Two event kinds matter for cost intelligence:

* ``assistant`` events carry a ``usage`` block (tokens) and a ``model`` -> cost.
* ``user`` events carry prompt text -> used by waste detectors (duplicate
  prompts, prompt-volume analytics).

Everything else (tool results, summaries, meta) is ignored for cost but the
prompt text of user turns is hashed so we can spot repeats without storing the
raw text in reports.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator

from . import pricing

_TS_RE = re.compile(r"(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$")


def _parse_ts(value) -> datetime | None:
    """Parse an ISO-8601 timestamp robustly across Python 3.9–3.12.

    Python < 3.11 only accepts 3- or 6-digit fractional seconds from
    ``fromisoformat``; we normalize the fraction to 6 digits so real Claude
    Code logs (millisecond precision, trailing ``Z``) parse everywhere.
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        mm = _TS_RE.match(v)
        if mm:
            frac = mm.group(2) or ""
            if frac:
                frac = "." + frac[1:][:6].ljust(6, "0")
            try:
                dt = datetime.fromisoformat(mm.group(1) + frac + mm.group(3))
            except ValueError:
                dt = None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _project_name(cwd: str | None, source_file: str) -> str:
    """Derive a stable, human display name for the project."""
    if cwd:
        norm = cwd.replace("\\", "/").rstrip("/")
        base = os.path.basename(norm)
        if base:
            return base
        # cwd was a drive root like "D:/": fall back to the drive label
        return norm.rstrip(":/") or norm or "root"
    # last resort: the sanitized directory name Claude Code used
    return os.path.basename(os.path.dirname(source_file)) or "unknown"


def _flatten_text(content) -> str:
    """Pull human text out of a message ``content`` field (str or block list)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""


@dataclass
class Event:
    kind: str               # "assistant" | "user"
    session_id: str
    project: str
    ts: datetime | None
    model: str = ""
    # token components
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0
    # cost (USD), filled for assistant events
    cost: float = 0.0
    priced: bool = True
    # user-prompt fields
    prompt_hash: str = ""
    prompt_len: int = 0
    # bookkeeping
    is_error: bool = False
    request_id: str = ""
    uuid: str = ""


def _usage_tokens(usage: dict) -> tuple[int, int, int, int, int]:
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    cw_total = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cw5 = cw1h = 0
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        cw5 = int(split.get("ephemeral_5m_input_tokens", 0) or 0)
        cw1h = int(split.get("ephemeral_1h_input_tokens", 0) or 0)
    if cw5 == 0 and cw1h == 0:
        # no split available -> treat all cache writes as 5-minute TTL
        cw5 = cw_total
    return inp, out, cw5, cw1h, cr


def normalize(records: Iterable[dict]) -> Iterator[Event]:
    """Yield :class:`Event` objects from raw ingest records."""
    for rec in records:
        rtype = rec.get("type")
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        _src = os.path.basename(rec.get("_source_file", ""))
        if _src.endswith(".jsonl"):
            _src = _src[: -len(".jsonl")]
        session_id = rec.get("sessionId") or _src
        project = _project_name(rec.get("cwd"), rec.get("_source_file", ""))
        ts = _parse_ts(rec.get("timestamp"))

        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
        if rtype == "assistant" and usage:
            inp, out, cw5, cw1h, cr = _usage_tokens(usage)
            model = msg.get("model", "") or ""
            p = pricing.resolve(model)
            cost = pricing.cost_of(model, inp, out, cw5, cw1h, cr)
            stop = msg.get("stop_reason")
            is_err = bool(rec.get("isApiErrorMessage")) or stop in {"error", "max_tokens"}
            yield Event(
                kind="assistant",
                session_id=session_id,
                project=project,
                ts=ts,
                model=model,
                input_tokens=inp,
                output_tokens=out,
                cache_write_5m=cw5,
                cache_write_1h=cw1h,
                cache_read=cr,
                cost=cost,
                priced=p.priced,
                is_error=is_err,
                request_id=rec.get("requestId", "") or "",
                uuid=rec.get("uuid", "") or "",
            )
        elif rtype == "user":
            text = _flatten_text(msg.get("content"))
            if not text:
                continue
            # meta side-channels (tool results, command stdout) are not prompts
            if text.startswith("<") and text.endswith(">"):
                continue
            h = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]
            yield Event(
                kind="user",
                session_id=session_id,
                project=project,
                ts=ts,
                prompt_hash=h,
                prompt_len=len(text),
                uuid=rec.get("uuid", "") or "",
            )


def collect(records: Iterable[dict]) -> list[Event]:
    """Eagerly normalize into a list (most callers want a reusable list)."""
    return list(normalize(records))
