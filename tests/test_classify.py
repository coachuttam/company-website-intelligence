"""Tests for the optional Jev decision layer (B-62). Offline: the Jev client is a stub."""
import httpx
import pytest

from wi.classify.decisions import apply_classifier, parse_choice
from wi.classify.jev import JevClient, JevError, JevResult
from wi.crawl.clean import CleanPage
from wi.extract.pipeline import ExtractionRun
from wi.schemas.claim import Claim, Coverage, Status

PRICING_HYBRID = (
    "Pricing\nFree\n$0 per member / month\nEnterprise\nCustom pricing\n"
    "Buttons and links on this page:\nGet Notion free\nContact sales"
)
PRICING_SELF_ONLY = "Pricing\nStarter $29/month\nButtons and links on this page:\nStart free trial"
PRICING_NO_BLOCK = "Pricing\nFree\n$0 per member / month"

CFG = {"classifier": {"provider": "jev", "mode": "override", "min_probability": 0.8,
                       "jev": {"price_usd_per_1m_input": 0.042}}}
OPTS = ["self_serve", "sales_led", "hybrid", "unclear"]


class StubClient:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def evaluate(self, state, questions):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return JevResult(model="jev-test", answers={"sales_motion": self.answer},
                         input_tokens=1000, output_tokens=5, elapsed_s=0.4)


def answer(choice, p=0.95):
    rest = {o: (1 - p) / 3 for o in OPTS if o != choice}
    return {"probabilities": {choice: p, **rest}}


def page(text, url="https://x.com/pricing"):
    return CleanPage(url=url, title="Pricing", text=text)


def existing_claim(status=Status.inferred, value="Self-serve signup"):
    if status == Status.not_found:
        return Claim(claim_id="x:pricing.sales_motion:0", field="pricing.sales_motion",
                     status=status, coverage=Coverage(page_types_checked=["pricing"], pages_checked=1))
    return Claim(claim_id="x:pricing.sales_motion:0", field="pricing.sales_motion", value=value,
                 status=status, source_url="https://x.com/pricing", evidence="Get Notion free",
                 retrieved_at="2026-10-06", notes="cue")


def run_with(claim):
    return ExtractionRun(site_url="https://x.com", claims=[claim] if claim else [])


def sm(run):
    return next(c for c in run.claims if c.field == "pricing.sales_motion")


def test_off_by_default_makes_no_call():
    client = StubClient(answer("hybrid"))
    report = apply_classifier(run_with(existing_claim()), [page(PRICING_HYBRID)], {}, "2026-10-06", client)
    assert report == {"provider": "none", "enabled": False} and client.calls == []


def test_hybrid_applied_with_real_evidence_lines():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06", StubClient(answer("hybrid")))
    c = sm(run)
    assert report["decisions"][0]["applied"] is True
    assert c.status == Status.inferred and "contact" in c.value.lower() and "self-serve" in c.value.lower()
    assert c.evidence.split("\n") == ["Get Notion free", "Contact sales"]
    assert c.confidence == pytest.approx(0.95) and c.notes
    assert report["estimated_cost_usd"] == pytest.approx(0.000042)


def test_below_threshold_not_applied():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06", StubClient(answer("hybrid", 0.6)))
    assert report["decisions"][0]["applied"] is False and sm(run).value == "Self-serve signup"


def test_unclear_not_applied():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06", StubClient(answer("unclear")))
    assert report["decisions"][0]["applied"] is False


def test_no_pricing_page_means_no_call():
    client = StubClient(answer("hybrid"))
    report = apply_classifier(run_with(existing_claim()), [page(PRICING_HYBRID, "https://x.com/about")],
                              CFG, "2026-10-06", client)
    assert client.calls == [] and report["decisions"][0]["applied"] is False


def test_hybrid_needs_both_cue_kinds_on_the_page():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_SELF_ONLY)], CFG, "2026-10-06", StubClient(answer("hybrid")))
    assert report["decisions"][0]["applied"] is False and sm(run).value == "Self-serve signup"


def test_choice_without_any_cue_lines_not_applied():
    run = run_with(existing_claim(Status.not_found))
    report = apply_classifier(run, [page(PRICING_NO_BLOCK)], CFG, "2026-10-06", StubClient(answer("self_serve")))
    assert report["decisions"][0]["applied"] is False and sm(run).status == Status.not_found


def test_self_serve_contradicted_by_a_contact_cue_not_applied():
    run = run_with(existing_claim(Status.not_found))
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06", StubClient(answer("self_serve")))
    assert report["decisions"][0]["applied"] is False


def test_self_serve_applied_when_only_self_serve_cues():
    run = run_with(existing_claim(Status.not_found))
    apply_classifier(run, [page(PRICING_SELF_ONLY)], CFG, "2026-10-06", StubClient(answer("self_serve")))
    assert sm(run).status == Status.inferred and sm(run).value == "Self-serve signup"


def test_fill_missing_keeps_an_existing_answer_and_skips_the_call():
    cfg = {"classifier": {**CFG["classifier"], "mode": "fill_missing"}}
    client = StubClient(answer("hybrid"))
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], cfg, "2026-10-06", client)
    assert client.calls == [] and sm(run).value == "Self-serve signup"
    assert report["decisions"][0]["applied"] is False


def test_fill_missing_fills_a_not_found():
    cfg = {"classifier": {**CFG["classifier"], "mode": "fill_missing"}}
    run = run_with(existing_claim(Status.not_found))
    apply_classifier(run, [page(PRICING_HYBRID)], cfg, "2026-10-06", StubClient(answer("hybrid")))
    assert sm(run).status == Status.inferred


def test_jev_error_leaves_extraction_untouched():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06",
                              StubClient(error=JevError("HTTP 500")))
    assert "HTTP 500" in report["error"] and sm(run).value == "Self-serve signup"


def test_missing_key_degrades_gracefully(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06")
    assert "JEV_API_KEY" in report["error"] and sm(run).value == "Self-serve signup"


def test_unknown_answer_shape_not_applied_and_raw_kept():
    run = run_with(existing_claim())
    report = apply_classifier(run, [page(PRICING_HYBRID)], CFG, "2026-10-06", StubClient({"weird": 1}))
    d = report["decisions"][0]
    assert d["applied"] is False and d["raw"] == {"weird": 1}


@pytest.mark.parametrize("raw, expected", [
    ({"probabilities": {"hybrid": 0.7, "unclear": 0.3}}, ("hybrid", 0.7)),
    ({"hybrid": 0.9, "unclear": 0.1}, ("hybrid", 0.9)),
    ({"choice": "sales_led", "probability": 0.88}, ("sales_led", 0.88)),
    ({"choice": "sales_led"}, None),
    ("hybrid", None),
])
def test_parse_choice_shapes(raw, expected):
    assert parse_choice(raw, OPTS) == expected


def test_client_sends_model_state_questions_and_never_leaks_the_key():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"q": {}},
                                         "usage": {"input_tokens": 12, "output_tokens": 1}})

    client = JevClient(api_key="SECRET", client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = client.evaluate("state", {"q": {"type": "choice"}})
    assert res.input_tokens == 12 and seen["auth"] == "Bearer SECRET"
    assert b'"model":"jev-latest"' in seen["body"].replace(b" ", b"")

    bad = JevClient(api_key="SECRET", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(422, text="missing model"))))
    with pytest.raises(JevError) as e:
        bad.evaluate("s", {})
    assert "SECRET" not in str(e.value)


# ---- B-68: pricing.revenue_model decision (rides in the same Jev call) --------------------------
from wi.classify.decisions import recurring_price_lines  # noqa: E402

REV_OPTS = ["subscription", "usage_based", "one_time", "unclear"]
REV_CFG = {"classifier": {**CFG["classifier"], "revenue_model": {"enabled": True, "mode": "fill_missing"}}}
PRICING_RECURRING = ("Pricing\nFree\n$0 per member / month\nPlus\n$10 per member / month\n"
                     "$20 per member / month\nSave up to 20% with yearly\n"
                     "Buttons and links on this page:\nGet Notion free\nContact sales")


class TwoAnswerStub(StubClient):
    def __init__(self, sales, revenue):
        super().__init__(None)
        self.sales, self.revenue = sales, revenue

    def evaluate(self, state, questions):
        self.calls.append((state, questions))
        return JevResult(model="jev-test", answers={"sales_motion": self.sales,
                                                    "revenue_model": self.revenue},
                         input_tokens=1000, output_tokens=5, elapsed_s=0.4)


def rev_claim(status=Status.not_found):
    if status == Status.not_found:
        return Claim(claim_id="x:pricing.revenue_model:0", field="pricing.revenue_model",
                     status=status, coverage=Coverage(page_types_checked=["pricing"], pages_checked=1))
    return Claim(claim_id="x:pricing.revenue_model:0", field="pricing.revenue_model", value="usage-based",
                 status=status, source_url="https://x.com/pricing", evidence="$10 per member / month",
                 retrieved_at="2026-10-06", notes="n")


def rm(run):
    return next(c for c in run.claims if c.field == "pricing.revenue_model")


def rev_answer(choice, p=0.95):
    rest = {o: (1 - p) / 3 for o in REV_OPTS if o != choice}
    return {"probabilities": {choice: p, **rest}}


def test_revenue_model_is_off_unless_enabled():
    client = StubClient(answer("hybrid"))
    run = run_with(existing_claim())
    apply_classifier(run, [page(PRICING_RECURRING)], CFG, "2026-10-06", client)
    assert len(client.calls) == 1 and list(client.calls[0][1]) == ["sales_motion"]


def test_one_call_carries_both_questions_and_both_apply():
    client = TwoAnswerStub(answer("hybrid"), rev_answer("subscription"))
    run = ExtractionRun(site_url="https://x.com", claims=[existing_claim(), rev_claim()])
    report = apply_classifier(run, [page(PRICING_RECURRING)], REV_CFG, "2026-10-06", client)
    assert len(client.calls) == 1 and set(client.calls[0][1]) == {"sales_motion", "revenue_model"}
    c = rm(run)
    assert c.status == Status.inferred and c.value == "Subscription"
    assert c.evidence.split("\n") == ["$10 per member / month", "$20 per member / month"]
    assert [d["applied"] for d in report["decisions"]] == [True, True]


def test_revenue_model_fill_missing_keeps_an_existing_answer_and_asks_nothing_extra():
    client = TwoAnswerStub(answer("hybrid"), rev_answer("subscription"))
    run = ExtractionRun(site_url="https://x.com", claims=[existing_claim(), rev_claim(Status.inferred)])
    apply_classifier(run, [page(PRICING_RECURRING)], REV_CFG, "2026-10-06", client)
    assert list(client.calls[0][1]) == ["sales_motion"] and rm(run).value == "usage-based"


def test_revenue_model_non_subscription_choice_is_not_applied():
    client = TwoAnswerStub(answer("hybrid"), rev_answer("usage_based"))
    run = ExtractionRun(site_url="https://x.com", claims=[existing_claim(), rev_claim()])
    report = apply_classifier(run, [page(PRICING_RECURRING)], REV_CFG, "2026-10-06", client)
    assert rm(run).status == Status.not_found and report["decisions"][1]["applied"] is False


def test_revenue_model_subscription_needs_a_real_recurring_price_line():
    client = TwoAnswerStub(answer("hybrid"), rev_answer("subscription"))
    text = "Pricing\nCustom pricing\nButtons and links on this page:\nGet started free\nContact sales"
    run = ExtractionRun(site_url="https://x.com", claims=[existing_claim(), rev_claim()])
    report = apply_classifier(run, [page(text)], REV_CFG, "2026-10-06", client)
    assert rm(run).status == Status.not_found and report["decisions"][1]["applied"] is False


def test_revenue_model_below_threshold_not_applied():
    client = TwoAnswerStub(answer("hybrid"), rev_answer("subscription", 0.6))
    run = ExtractionRun(site_url="https://x.com", claims=[existing_claim(), rev_claim()])
    apply_classifier(run, [page(PRICING_RECURRING)], REV_CFG, "2026-10-06", client)
    assert rm(run).status == Status.not_found


@pytest.mark.parametrize("line, expected", [
    ("$10 per member / month", True), ("$18 per user / month", True), ("28 USD/mo", True),
    ("379USD/mo after 14 days", True), ("₹499 / month", True), ("$10/seat/mo", True),
    ("Starts at $15K/yr", True), ("$0 per member / month", False), ("Save up to 20%", False),
    ("Billed monthly", False), ("Custom pricing", False),
    ("₹3.00 per 1,000 characters", False), ("2% + GST per transaction", False),
])
def test_recurring_price_lines(line, expected):
    assert bool(recurring_price_lines(line)) is expected
