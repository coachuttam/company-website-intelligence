"""B-99: the optional category-normalised metric (wi/eval/normalise.py, docs/SCORING.md).
Pure functions and fake run files only: no model call, no semantic judge."""
from __future__ import annotations

import json

from eval.baseline import run_scoring_set
from wi.eval.normalise import (
    CORRECT_NORMALISED, CORRECT_PARTIAL_NORMALISED, NORMALISED_VERDICTS, apply_normalisation,
    delivery_category, normalised_summary, normalised_verdict, revenue_categories,
)
from wi.eval.scoring import FieldScore, Verdict
from wi.extract.fields import FIELDS
from wi.schemas.claim import Claim, Status

DM, RM = "products.delivery_model", "pricing.revenue_model"


def _fs(field, label, system, verdict=Verdict.incorrect):
    return FieldScore(field=field, verdict=verdict, label_status="inferred", label_value=label,
                      system_status="inferred", system_value=system, system_claim_id="c:1")


# rule B
def test_delivery_category_rules():
    assert delivery_category("Software: API-first platform") == "software"
    assert delivery_category("software (API)") == "software"
    assert delivery_category("  Services firm") == "service"
    assert delivery_category("Digital software delivered online") == "software"   # first whole word
    assert delivery_category("an online marketplace for physical goods") == "marketplace"
    assert delivery_category("softwares") is None and delivery_category("Cloud platform") is None
    assert normalised_verdict(_fs(DM, "Software: API-first platform", "software (API)")) == CORRECT_NORMALISED
    assert normalised_verdict(_fs(DM, "Service: consulting", "software")) is None


# rule C
def test_revenue_category_sets():
    assert revenue_categories("Subscription tiers plus transaction fees") == {"subscription", "transaction"}
    assert revenue_categories("transaction-based") == {"transaction"}
    assert revenue_categories("Usage-based: pay-as-you-go API billing") == {"usage"}
    assert revenue_categories("Per-seat subscription") == {"subscription"}
    assert revenue_categories("Custom enterprise pricing") == frozenset()


def test_revenue_verdicts_full_partial_and_none():
    assert normalised_verdict(_fs(RM, "Transaction fees: percentage fee on payments", "transaction-based")) == CORRECT_NORMALISED
    assert normalised_verdict(_fs(RM, "Subscription tiers plus transaction fees", "subscription")) == CORRECT_PARTIAL_NORMALISED
    assert normalised_verdict(_fs(RM, "Subscription", "pay-as-you-go")) is None            # disjoint
    assert normalised_verdict(_fs(RM, "Custom enterprise pricing", "subscription")) is None  # no category


# rule A
def test_only_incorrect_changes_and_nothing_is_downgraded():
    for v in Verdict:
        s = _fs(DM, "Software: x", "software", verdict=v)
        assert normalised_verdict(s) == (CORRECT_NORMALISED if v == Verdict.incorrect else None)
    other = _fs("customers.segments", "Software teams", "software teams")
    assert normalised_verdict(other) is None
    scores = [_fs(DM, "Software: x", "software"), _fs(RM, "Subscription", "subscription", Verdict.correct),
              _fs(RM, "x", "y", Verdict.miss)]
    pairs = apply_normalisation(scores)
    assert [s.verdict for s, _ in pairs] == [Verdict.incorrect, Verdict.correct, Verdict.miss]   # not mutated
    summary = normalised_summary(scores)
    assert summary["right_calls"] == summary["strict_right_calls"] + 1 >= summary["strict_right_calls"]


def test_new_verdict_names_are_not_strict_verdicts():
    assert not set(NORMALISED_VERDICTS) & {v.value for v in Verdict}


# rule D: the default report is unchanged; the flag only adds a key
def _fixture(tmp_path, monkeypatch):
    monkeypatch.setattr("eval.baseline.ROOT", tmp_path)
    labels, runs = tmp_path / "labels", tmp_path / "runs"
    labels.mkdir()
    runs.mkdir()
    fields = {f: {"status": "not_found"} for f in FIELDS}
    fields[DM] = {"status": "inferred", "value": "Software: a web app"}
    fields[RM] = {"status": "inferred", "value": "Subscription tiers plus transaction fees"}
    (labels / "a.json").write_text(json.dumps({"fields": fields}))
    claims = [Claim(claim_id=f"a:{f}", field=f, status=Status.inferred, value=v, evidence=v,
                    source_url="https://a.example/", page_title="A", retrieved_at="2026-10-11",
                    notes="fixture").model_dump(mode="json")
              for f, v in ((DM, "software"), (RM, "subscription"))]
    (runs / "a_run.json").write_text(json.dumps({"claims": claims}))
    return labels, runs


def test_report_is_unchanged_without_the_flag_and_only_gains_a_key_with_it(tmp_path, monkeypatch, capsys):
    labels, runs = _fixture(tmp_path, monkeypatch)
    kw = dict(site_set=[("a.json", "a_run.json")], label_dir=labels, run_dir=runs, set_key="x",
              per_field_heading="x")
    plain, _ = run_scoring_set(report_path=tmp_path / "plain.json", **kw)
    out_plain = capsys.readouterr().out
    norm, _ = run_scoring_set(report_path=tmp_path / "norm.json", normalised=True, **kw)
    out_norm = capsys.readouterr().out
    assert "normalised" not in plain and "category-normalised" not in out_plain
    text = (tmp_path / "plain.json").read_text()
    assert not any(name in text for name in NORMALISED_VERDICTS)
    assert {k: v for k, v in norm.items() if k != "normalised"} == plain
    assert norm["normalised"]["upgraded_by_field"] == {
        DM: {CORRECT_NORMALISED: 1, CORRECT_PARTIAL_NORMALISED: 0},
        RM: {CORRECT_NORMALISED: 0, CORRECT_PARTIAL_NORMALISED: 1}}
    assert norm["normalised"]["right_calls"] == norm["normalised"]["strict_right_calls"] + 2
    assert "category-normalised (post-hoc, secondary" in out_norm
    assert out_norm.startswith(out_plain.split("\nWrote ")[0])   # strict printout unchanged before the block


def test_held_out_v2_passes_the_flag_through(tmp_path, monkeypatch):
    from eval.checksum_labels import write
    from eval.held_out import main_v2
    labels, runs = _fixture(tmp_path, monkeypatch)
    doc = json.loads((labels / "a.json").read_text())
    doc["labeling_metadata"] = {"company_name": "A", "website_url": "https://a.example/", "split": "held_out_v2",
                                "date_labeled": "2026-10-11"}
    (labels / "a.json").write_text(json.dumps(doc))
    (runs / "a_run.json").rename(runs / "a_example.json")
    sums = tmp_path / "labels_v2.sha256"
    assert write(labels, sums)[0]
    assert main_v2([], labels, sums, runs, tmp_path / "r1.json") == 0
    assert main_v2(["--normalised"], labels, sums, runs, tmp_path / "r2.json") == 0
    assert "normalised" not in json.loads((tmp_path / "r1.json").read_text())
    assert json.loads((tmp_path / "r2.json").read_text())["normalised"]["upgraded_fields"] == 2
