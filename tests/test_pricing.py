"""wi/extract/pricing.py: pure token-count -> USD math, no network, no model calls."""
import pytest

from wi.extract.pricing import estimate_cost_usd

PRICING = {"gpt-4o-mini": {"input": 0.15, "output": 0.60}}


def test_known_model_matches_hand_computed_price():
    # 34,911 prompt + 1,262 completion tokens is the real Day 5 baseline run (PROGRESS.md,
    # basecamp.com, gpt-4o-mini) -- hand-computed at $0.15/$0.60 per 1M tokens:
    # 34911/1e6*0.15 + 1262/1e6*0.60 = 0.00523665 + 0.0007572 = 0.00599385
    cost = estimate_cost_usd(34911, 1262, "gpt-4o-mini", PRICING)
    assert cost == pytest.approx(0.00599385)


def test_zero_tokens_is_zero_cost():
    assert estimate_cost_usd(0, 0, "gpt-4o-mini", PRICING) == 0.0


def test_unpriced_model_returns_none_not_zero():
    # A model missing from config.yaml's llm.pricing_usd_per_1m_tokens must come back as
    # "unknown" (None), never a silent $0.00 -- that would misreport a real cost as free.
    assert estimate_cost_usd(10000, 1000, "some-future-model", PRICING) is None


def test_output_tokens_priced_higher_than_input_tokens():
    # Sanity check on the price table shape itself: for gpt-4o-mini (and every OpenAI chat
    # model so far), a completion token costs more than a prompt token.
    same_count_input_cost = estimate_cost_usd(1000, 0, "gpt-4o-mini", PRICING)
    same_count_output_cost = estimate_cost_usd(0, 1000, "gpt-4o-mini", PRICING)
    assert same_count_output_cost > same_count_input_cost
