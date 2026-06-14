import math

from cci import pricing


def approx(a, b, eps=1e-9):
    return math.isclose(a, b, abs_tol=eps)


def test_base_rates_per_mtok():
    assert approx(pricing.cost_of("claude-opus-4-8", input_tokens=1_000_000), 15.0)
    assert approx(pricing.cost_of("claude-opus-4-8", output_tokens=1_000_000), 75.0)
    assert approx(pricing.cost_of("claude-sonnet-4-6", input_tokens=1_000_000), 3.0)
    assert approx(pricing.cost_of("claude-sonnet-4-6", output_tokens=1_000_000), 15.0)
    assert approx(pricing.cost_of("claude-haiku-4-5", input_tokens=1_000_000), 1.0)


def test_cache_multipliers():
    assert approx(pricing.cost_of("claude-opus-4-8", cache_read=1_000_000), 1.5)
    assert approx(pricing.cost_of("claude-opus-4-8", cache_write_5m=1_000_000), 18.75)
    assert approx(pricing.cost_of("claude-opus-4-8", cache_write_1h=1_000_000), 30.0)


def test_model_resolution():
    assert pricing.resolve("claude-opus-4-8").key == "opus"
    assert pricing.resolve("claude-sonnet-4-6").key == "sonnet"
    assert pricing.resolve("claude-haiku-4-5-20251001").input == 1.0
    assert pricing.resolve("claude-3-5-haiku-20241022").input == 0.80
    assert pricing.resolve("claude-3-haiku-20240307").input == 0.25
    assert pricing.resolve("opus").cheaper == "sonnet"
    assert pricing.resolve("sonnet").cheaper == "haiku"
    assert pricing.resolve("haiku").cheaper is None


def test_unpriced_model_flagged_zero():
    p = pricing.resolve("<synthetic>")
    assert not p.priced
    assert pricing.cost_of("<synthetic>", input_tokens=1_000_000) == 0.0


def test_breakdown_sums_to_total():
    args = dict(input_tokens=1234, output_tokens=567, cache_write_5m=890,
                cache_write_1h=42, cache_read=9999)
    bd = pricing.cost_breakdown("claude-opus-4-8", **args)
    total = pricing.cost_of("claude-opus-4-8", **args)
    assert approx(sum(bd.values()), total)


def test_overrides_apply_and_restore():
    before = pricing.resolve("opus").input
    pricing.merge_overrides({"opus": {"input": 99, "output": 199}})
    assert pricing.resolve("opus").input == 99
    assert approx(pricing.cost_of("claude-opus-4-8", input_tokens=1_000_000), 99.0)
    # restore so other tests are unaffected
    pricing.merge_overrides({"opus": {"input": before, "output": 75.0}})
    assert pricing.resolve("opus").input == before
