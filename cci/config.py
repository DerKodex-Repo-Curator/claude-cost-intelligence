"""Config loader: budgets, pricing overrides, project aliases.

Resolution order (first hit wins for each key):

1. explicit ``--config <path>``
2. ``./cci.config.json`` in the working directory
3. ``~/.config/cci/config.json``
4. environment: ``CCI_MONTHLY_BUDGET``

Config is optional — CCI works with none. Example file::

    {
      "monthly_budget": 200,
      "warn_at": 0.8,
      "pricing": { "opus": { "input": 12, "output": 60 } },
      "aliases": { "D-": "my-main-repo" }
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULTS = {
    "monthly_budget": None,   # USD; None = no budget set
    "warn_at": 0.8,           # fraction of budget that triggers a warning
    "pricing": {},            # {model_key: {"input": x, "output": y}}
    "aliases": {},            # {raw_project: display_name}
}


def _candidates(explicit: str | None) -> list[Path]:
    paths = []
    if explicit:
        paths.append(Path(explicit))
    paths.append(Path.cwd() / "cci.config.json")
    paths.append(Path.home() / ".config" / "cci" / "config.json")
    return paths


def load(explicit: str | None = None) -> dict:
    cfg = dict(DEFAULTS)
    for path in _candidates(explicit):
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cfg.update({k: v for k, v in data.items() if v is not None})
                    cfg["_source"] = str(path)
                    break
            except (ValueError, OSError):
                continue
    env_budget = os.environ.get("CCI_MONTHLY_BUDGET")
    if env_budget and cfg.get("monthly_budget") is None:
        try:
            cfg["monthly_budget"] = float(env_budget)
        except ValueError:
            pass
    return cfg


def budget_status(cfg: dict, projection: dict) -> dict | None:
    """Compare projected/MTD spend against the configured budget."""
    budget = cfg.get("monthly_budget")
    if not budget or not projection.get("available"):
        return None
    mtd = projection["month_to_date"]
    proj = projection["projected_month"]
    warn_at = cfg.get("warn_at", 0.8)
    pct_proj = proj / budget if budget else 0.0
    if pct_proj >= 1.0:
        state = "over"
    elif pct_proj >= warn_at:
        state = "warn"
    else:
        state = "ok"
    return {
        "budget": budget,
        "month_to_date": mtd,
        "projected_month": proj,
        "pct_used_mtd": round(mtd / budget, 4) if budget else 0.0,
        "pct_projected": round(pct_proj, 4),
        "warn_at": warn_at,
        "state": state,
        "headroom": round(budget - proj, 2),
    }
