"""Data ingestion: read Claude Code session logs (JSONL) from disk.

Claude Code writes one JSONL file per session under
``~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl``. Each line is a JSON
record (assistant turn, user turn, tool result, meta, ...). We stream them
line-by-line so multi-GB histories never blow up memory.

Local-first: nothing leaves the machine. The only input is a directory (or a
single file) of JSONL. Malformed lines are counted and skipped, never crash.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


def default_logs_dir() -> Path:
    """Standard Claude Code projects directory for the current user."""
    env = os.environ.get("CCI_LOGS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "projects"


@dataclass
class IngestStats:
    files: int = 0
    lines: int = 0
    parsed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def iter_jsonl_files(root: Path) -> Iterator[Path]:
    """Yield every ``*.jsonl`` file under ``root`` (or ``root`` itself)."""
    if root.is_file():
        if root.suffix == ".jsonl":
            yield root
        return
    if not root.exists():
        return
    yield from sorted(root.rglob("*.jsonl"))


def read_records(root: Path, stats: IngestStats | None = None) -> Iterator[dict]:
    """Stream parsed JSON records from all JSONL files under ``root``.

    Each yielded dict is augmented with ``_source_file`` (str) so downstream
    code can attribute a record to its session file even when the embedded
    ``sessionId`` is absent.
    """
    st = stats if stats is not None else IngestStats()
    for path in iter_jsonl_files(root):
        st.files += 1
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    st.lines += 1
                    try:
                        rec = json.loads(line)
                    except (ValueError, json.JSONDecodeError):
                        st.skipped += 1
                        continue
                    if not isinstance(rec, dict):
                        st.skipped += 1
                        continue
                    st.parsed += 1
                    rec["_source_file"] = str(path)
                    yield rec
        except OSError as exc:  # pragma: no cover - filesystem edge
            st.errors.append(f"{path}: {exc}")
