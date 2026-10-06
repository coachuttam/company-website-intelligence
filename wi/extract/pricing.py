"""Per-token USD list prices for the models this project calls, and a pure function to turn
one run's token usage into an estimated dollar cost. Kept in its own file, separate from
wi/extract/llm.py (which calls the model) and run_site.py (which prints the result), so a
price change or a new model being added never touches either of those.

The actual prices live in config.yaml (llm.pricing_usd_per_1m_tokens), not here -- this file
is just the pure math, consistent with the project's own rule that tunable numbers live in
config, never in code (see config.yaml's header comment).

These are OpenAI's public per-1,000,000-token list prices, not the account's actual invoice:
no volume discount, no prompt-caching discount, and no allowance for the (much smaller)
semantic-judge calls eval/baseline.py and eval/held_out.py make separately. Treat the number
this produces as a same-order-of-magnitude estimate for cost-benefit conversations (compared
against config.yaml's targets.cost_mean_usd / cost_p95_usd), not a billing reconciliation.
"""
from __future__ import annotations

from typing import Dict, Optional


def estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    pricing_usd_per_1m: Dict[str, Dict[str, float]],
) -> Optional[float]:
    """Returns the estimated USD cost of one call, or None if `model` has no entry in
    `pricing_usd_per_1m` (config.yaml's llm.pricing_usd_per_1m_tokens) -- callers should show
    "cost unknown" in that case rather than silently printing $0.00 for an unpriced model."""
    price = pricing_usd_per_1m.get(model)
    if price is None:
        return None
    return ((prompt_tokens / 1_000_000) * price["input"]
             + (completion_tokens / 1_000_000) * price["output"])
