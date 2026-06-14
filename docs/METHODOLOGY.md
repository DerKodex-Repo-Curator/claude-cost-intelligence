# Methodology

> Every number CCI shows is computed from your local logs with the formulas
> below. Nothing is sent anywhere. Nothing is faked. Where a number is an
> estimate, it is labelled `estimated` and shown as a low–high band.

This document is the contract. If a figure in the dashboard or report ever
disagrees with the math here, that is a bug — please file it.

---

## 1. Where the data comes from

CCI reads Claude Code session logs: newline-delimited JSON (`.jsonl`) under
`~/.claude/projects/**`. Each assistant turn carries a `message.usage` block and
a `message.model`; each user turn carries prompt text. That is the entire input.

| Field used | Source |
|---|---|
| `input_tokens`, `output_tokens` | `message.usage` |
| `cache_creation_input_tokens` (+ 5m/1h split) | `message.usage.cache_creation` |
| `cache_read_input_tokens` | `message.usage` |
| `model` | `message.model` |
| `timestamp`, `sessionId`, `cwd` | record top level |

Malformed lines are skipped and counted, never silently merged.

---

## 2. Pricing (exact)

Prices are USD per **1,000,000 tokens (MTok)**, matching Anthropic's published
list prices. They live in [`cci/pricing.py`](../cci/pricing.py) and can be
overridden per-model via `--pricing` or `cci.config.json`.

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| Claude Opus (4.x / 3-opus) | 15.00 | 75.00 |
| Claude Sonnet (3.5 / 4.x) | 3.00 | 15.00 |
| Claude Haiku 4.x | 1.00 | 5.00 |
| Claude 3.5 Haiku | 0.80 | 4.00 |
| Claude 3 Haiku | 0.25 | 1.25 |

**Cache multipliers** (Anthropic policy, applied to the base input price):

```
cache write, 5-minute TTL = 1.25 × input
cache write, 1-hour  TTL  = 2.00 × input
cache read                = 0.10 × input
```

**Per-request cost** is therefore exact:

```
cost = ( input·Pin + output·Pout
       + cw5m·Pin·1.25 + cw1h·Pin·2.00 + cread·Pin·0.10 ) / 1e6
```

If a model id has no price (e.g. a synthetic/aliased model), its cost is `0` and
it is flagged. Totals then explicitly warn that spend is understated — CCI never
pretends an unpriced model was free on purpose.

---

## 3. Aggregation (exact)

* **Total spend / tokens** = sum over all assistant turns.
* **By model / project** = sum grouped by `model` / project (basename of `cwd`).
* **By day** = sum grouped by UTC calendar date.
* **Sessions** = grouped by `sessionId`: cost, requests, tokens, first/last
  timestamp (→ duration), model mix, error count, cache-hit ratio.
* **Cache-hit ratio** = `cache_read / (input + cache_read + cache_write)`.
* **$/1k tokens** and **$/request** are derived efficiency ratios (lower = cheaper
  per unit of work).

All of the above are deterministic: same input → same output, bit for bit.

---

## 4. Concentration (Pareto, exact)

Sessions are ranked by cost; we report the cumulative share curve and:

* `sessions_to_half` — how many top sessions reach 50% of spend.
* `top1_share` — the single most expensive session's share.
* `top5pct_share`, `top10pct_share`.

This is a description of your data, not an estimate.

---

## 5. Projection (estimate)

```
daily_run_rate   = mean(cost over the trailing 7 days)
projected_month  = month_to_date + daily_run_rate × days_remaining_in_month
```

Labelled **estimate** everywhere. It assumes the recent run-rate continues; a
quiet or bursty week changes it. It is a planning aid, not a forecast guarantee.

---

## 6. Waste detection & savings

Each detector emits a finding with a **confidence**:

* `measured` — the pattern itself is exact (e.g. an identical prompt sent N
  times). The savings figure still models *future behaviour*, but the signal is
  not heuristic.
* `estimated` — detection and/or savings use a documented reduction range. Always
  shown as a low–high band.

Total **recoverable** = the sum of each finding's mid-point, with a band from the
sum of lows to the sum of highs. It is explicitly *not* a guarantee.

### 6.1 Duplicate prompts — `measured`
Within a single session, an identical prompt (≥40 chars) sent **3+ times** is a
retry loop / re-ask. Avoidable requests = occurrences − 1.
`savings ≈ avoidable_requests × avg_request_cost`, band ±40%.
*Cross-session reuse of the same prompt (a recurring task) is intentionally not
counted, so the metric never inflates on routine repeated work.*

### 6.2 Premium model on simple tasks — `estimated`
For each turn on a premium tier (Opus/Sonnet) whose output is below a threshold
(Opus < 200, Sonnet < 150 output tokens), compute the exact cost delta to the
next-cheaper tier at the **same token counts**. Recoverable = **30–80%** of the
summed delta (not 100%, because some short turns genuinely need the stronger
model). Heuristic — treat as a routing hint, not a verdict.

### 6.3 Oversized context — `estimated`
Sessions with ≥10 requests whose **average carried context** (input + cache read +
cache write) exceeds **80k tokens/turn**. Their context billing is summed;
recoverable = **15–30%** (achievable via `/compact`, pruning, fresh sessions).

### 6.4 Low prompt-cache hit rate — `estimated`
Sessions with ≥6 requests, cache-hit ratio < 35%, and > 200k fresh input tokens.
Half the fresh input beyond the first turn is assumed cacheable; caching converts
input price (1.0×) to cache-read (0.1×) → 0.9× saved. Recoverable = **25–75%** of
that. Conservative by design.

### 6.5 Errored / truncated turns — `measured`
Turns with `stop_reason` of `error`/`max_tokens` or an API-error flag. Their cost
is summed; recoverable band is 50–100% (truncated outputs are often re-run).

### 6.6 Spend concentration — `attention` (no $)
Surfaces the Pareto fact so you audit the few whale sessions first. No dollar
figure is attached.

### 6.7 Unpriced usage — `data` (no $)
Flags model ids with no price so you know totals are understated.

---

## 7. Thresholds

Every threshold in §6 is a named constant at the top of
[`cci/waste.py`](../cci/waste.py) (e.g. `OVERUSE_OPUS_OUTPUT`, `BLOAT_AVG_CONTEXT_TOK`).
They are auditable and overridable, not hidden magic numbers.

---

## 8. What is exact vs estimated — at a glance

| Quantity | Exact | Estimated |
|---|:---:|:---:|
| Cost per request, totals, by-model/project/day | ✅ | |
| Sessions, durations, cache-hit ratio | ✅ | |
| Pareto concentration | ✅ | |
| Duplicate-prompt / error detection | ✅ | |
| Savings from any detector | | ✅ |
| Month projection | | ✅ |

When in doubt, run `cci json` and check the raw numbers yourself.
