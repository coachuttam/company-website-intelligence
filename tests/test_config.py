"""Config sanity: the PRD's proposed parameters are present and caps exist."""
from wi.config import load_config


def test_config_has_prd_caps():
    cfg = load_config()
    assert cfg["crawl"]["max_pages"] == 40  # tuned up from the PRD's original 25, see B-48
    assert cfg["crawl"]["max_depth"] == 2
    assert cfg["llm"]["max_input_tokens_per_run"] == 60000  # tuned up alongside it, see B-48
    assert cfg["targets"]["cost_mean_usd"] == 0.10
    assert cfg["news"]["lookback_days"] == 90


def test_crawl_and_token_budget_raised_together_by_b48():
    # B-48 (2026-09-27): confirming B-47 live showed every re-crawled site hitting the old
    # 25-page cap exactly, with the enlarged B-47 priority tier turning that fixed budget into
    # a zero-sum tradeoff (plaid.com's crawl fetched the new /industries/* pages at the cost of
    # 5 unrelated fields that used to work). Raised together, not just max_pages alone -- see
    # config.yaml's own comments for why raising only the page count would just move the
    # bottleneck to _fit_pages_to_input_budget()'s token trim instead.
    cfg = load_config()
    assert cfg["crawl"]["max_pages"] > 25
    assert cfg["llm"]["max_input_tokens_per_run"] > 40000


def test_priority_url_keywords_widened_by_b47():
    # B-47 (2026-09-27): added after the held-out run's crawls showed gong.io/buffer.com/
    # plaid.com saturating their 25-page budget on case-study pages while never fetching
    # anything resembling a trust/security/certifications or industries page -- see
    # config.yaml's own comment for the full root-cause. Every original keyword is kept
    # (traction.named_customers was already doing reasonably well); these five are additive.
    cfg = load_config()
    keywords = cfg["crawl"]["priority_url_keywords"]
    for original in ("customer", "testimonial", "case-stud", "partner", "certif",
                      "pricing", "about", "client"):
        assert original in keywords
    for added in ("industr", "integrat", "trust", "secur", "complian"):
        assert added in keywords
