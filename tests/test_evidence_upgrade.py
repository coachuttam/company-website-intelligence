"""B-102: bare products.names quotes upgraded to sentence evidence (wi/extract/evidence_upgrade.py).
Fixtures and a fake completer only: no network, no model call."""
from __future__ import annotations

import json

from wi.crawl import cache as cache_module
from wi.crawl.clean import CleanPage
from wi.extract.evidence_upgrade import find_upgrade, upgrade_bare_product_quotes
from wi.extract.fields import FIELDS
from wi.extract.llm import LLMResult
from wi.extract.pipeline import diagnostics_from_run, extract_claims
from wi.schemas.claim import Claim, Status
from wi.validate.evidence import quote_in_page

CONFIG = {"llm": {"small_model": "gpt-4o-mini"}}
SENTENCE = "Growth Flow automates the follow-up for every lead your forms collect."


class Fake:
    def __init__(self, claims):
        self.claims = claims

    def complete(self, messages, model):
        return LLMResult(content=json.dumps({"claims": self.claims, "announcements": []}), model=model,
                         prompt_tokens=1, completion_tokens=1, total_tokens=2, elapsed_s=0.0)


def _claims(field="products.names", value=("Growth Flow",), evidence=("Growth Flow",), url="https://t.example/"):
    out = [{"field": f, "status": "not_found", "value": None, "confidence": None, "source_url": None,
            "page_title": None, "evidence": None, "notes": None, "coverage": None} for f in FIELDS]
    out[FIELDS.index(field)] = {"field": field, "status": "extracted", "value": list(value), "confidence": 0.9,
                                "source_url": url, "page_title": "T", "evidence": list(evidence), "notes": None,
                                "coverage": None}
    return out


def _run(pages, claims):
    return extract_claims("https://t.example/", pages, CONFIG, Fake(claims), retrieved_at="2026-10-11")


def _field(run, f):
    return next(c for c in run.claims if c.field == f)


def test_bare_quote_upgraded_to_a_sentence_and_verbatim():
    home = CleanPage(url="https://t.example/", title="T", text="Growth Flow\nPricing")
    feature = CleanPage(url="https://t.example/growth", title="G", text=f"Intro line here.\n{SENTENCE}\nMore.")
    run = _run([home, feature], _claims())
    c = _field(run, "products.names")
    assert c.status == Status.extracted and c.evidence == [SENTENCE]
    assert quote_in_page(SENTENCE, feature.text)
    assert run.evidence_upgrades == [{"field": "products.names", "value": "Growth Flow",
                                      "source_url": "https://t.example/growth", "quote": SENTENCE}]


def test_still_rejected_without_a_qualifying_sentence():
    texts = ["Growth Flow\nResearch Flow\nForms",                                        # short lines only
             "Growth Flow | Research Flow | Forms | Surveys | Quizzes made simple for teams",  # menu-like card line
             "[logo and image labels] Growth Flow | Acme helps every team grow faster today",
             "[site navigation] Growth Flow automates the follow-up for every lead here"]
    for text in texts:
        run = _run([CleanPage(url="https://t.example/", title="T", text=text)], _claims())
        assert _field(run, "products.names").status == Status.not_found, text
        assert any("repeated back" in r.reason for r in run.rejected) and run.evidence_upgrades == []


def test_loom_regression_fixture_still_rejects():
    page = CleanPage(url="https://loom.example/use-case", title="Use cases", text="Loom for Sales\nLoom for Support\n")
    run = _run([page], _claims(value=("Loom for Sales", "Loom for Support"),
                               evidence=("Loom for Sales", "Loom for Support"), url=page.url))
    assert _field(run, "products.names").status == Status.not_found and run.evidence_upgrades == []


def test_first_candidate_in_page_order_cited_page_first():
    first = "Growth Flow is the newest product we built for growth teams everywhere."
    cited = CleanPage(url="https://t.example/b", title="", text=f"x\n{first}")
    other = CleanPage(url="https://t.example/a", title="", text=SENTENCE)
    claim = Claim(claim_id="c", field="products.names", status=Status.extracted, value=["Growth Flow"],
                  evidence=["Growth Flow"], source_url=cited.url, page_title="", retrieved_at="2026-10-11")
    by_url = {"https://t.example/a": other.text, "https://t.example/b": cited.text}
    new, recs = upgrade_bare_product_quotes(claim, by_url)
    assert new.evidence == [first] and recs[0]["source_url"] == "https://t.example/b"


def test_long_line_uses_the_sentence_with_the_name():
    long_line = ("Lorem ipsum dolor sit amet. " * 12) + SENTENCE + " Other text follows here."
    assert find_upgrade("Growth Flow", long_line) == SENTENCE


def test_other_fields_and_non_bare_quotes_are_untouched():
    page = CleanPage(url="https://t.example/", title="T", text=f"Globex\n{SENTENCE}")
    run = _run([page], _claims(field="traction.named_customers", value=("Globex",), evidence=("Globex",)))
    assert _field(run, "traction.named_customers").evidence == ["Globex"] and run.evidence_upgrades == []
    good = "Growth Flow automates the follow-up for every lead your forms collect."
    claim = Claim(claim_id="c", field="products.names", status=Status.extracted, value=["Growth Flow"],
                  evidence=[good], source_url=page.url, page_title="", retrieved_at="2026-10-11")
    same, recs = upgrade_bare_product_quotes(claim, {"https://t.example/": page.text})
    assert same is claim and recs == []


def test_upgrades_in_run_json_are_ignored_by_loader_and_scorer(tmp_path):
    from eval.baseline import _load_claims
    from wi.eval.scoring import score_run
    feature = CleanPage(url="https://t.example/", title="T", text=SENTENCE)
    run = _run([feature], _claims())
    data = {"claims": [c.model_dump(mode="json") for c in run.claims], **diagnostics_from_run(run)}
    assert data["evidence_upgrades"]
    (tmp_path / "a.json").write_text(json.dumps(data))
    (tmp_path / "b.json").write_text(json.dumps({"claims": data["claims"]}))
    label = {"fields": {f: {"status": "not_found"} for f in FIELDS}}
    label["fields"]["products.names"] = {"status": "extracted", "value": ["Growth Flow"]}
    a, b = score_run(label, _load_claims(tmp_path / "a.json")), score_run(label, _load_claims(tmp_path / "b.json"))
    assert [(s.field, s.verdict) for s in a] == [(s.field, s.verdict) for s in b]


def test_version_28_changes_the_cache_key(monkeypatch):
    assert cache_module.EXTRACTION_LOGIC_VERSION == 28
    pages = [CleanPage(url="https://t.example/", title="T", text="x")]
    k28 = cache_module.run_fingerprint("https://t.example/", pages, {})
    monkeypatch.setattr(cache_module, "EXTRACTION_LOGIC_VERSION", 27)
    assert cache_module.run_fingerprint("https://t.example/", pages, {}) != k28
