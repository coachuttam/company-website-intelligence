"""B-97: eval/held_out.py's `--set v2` path. Fake labels and fake run files in tmp_path only:
no pipeline run, no model call, no network. One test reads the real held-out v2 label files to
check their count, URLs and field keys; nothing is scored against them."""
from __future__ import annotations

import json

from eval.checksum_labels import write
from eval.held_out import (
    HELD_OUT_LABEL_DIR, HELD_OUT_LABELS, _selected_set, main, main_v2, v2_sites,
)
from wi.extract.fields import FIELDS
from wi.schemas.claim import Claim, Status


def _label(label_dir, name, url, overrides=None):
    fields = {f: {"status": "not_found", "source_url": ""} for f in FIELDS}
    fields.update(overrides or {})
    doc = {"labeling_metadata": {"company_name": name.title(), "website_url": url, "split": "held_out_v2",
                                 "labeler": "test", "date_labeled": "2026-10-10", "notes": ""},
           "fields": fields}
    (label_dir / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")


def _claim(n, field, value, url):
    return Claim(claim_id=f"c:{n}", field=field, status=Status.extracted, value=value, source_url=url,
                 page_title="Fake", evidence=value, retrieved_at="2026-10-10").model_dump(mode="json")


def _run(run_dir, slug, claims):
    (run_dir / f"{slug}.json").write_text(json.dumps({"claims": claims}), encoding="utf-8")


def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("eval.baseline.ROOT", tmp_path)  # run_scoring_set prints paths relative to ROOT
    label_dir, run_dir = tmp_path / "labels", tmp_path / "runs"
    label_dir.mkdir()
    run_dir.mkdir()
    return label_dir, run_dir, tmp_path / "labels_v2.sha256", tmp_path / "report.json"


def test_default_set_is_still_the_old_ten_sites():
    assert _selected_set([]) == "v1" and _selected_set(["--semantic-judge"]) == "v1"
    assert _selected_set(["--set", "v2"]) == "v2" and _selected_set(["--set", "v1"]) == "v1"
    assert _selected_set(["--set", "v3"]) is None and _selected_set(["--set"]) is None
    assert HELD_OUT_LABEL_DIR.name == "heldout_v1_archived"
    assert [lf for lf, _ in HELD_OUT_LABELS] == [
        "razorpay.json", "buffer.json", "innovaccer.json", "sarvamai.json", "temenos.json",
        "thoughtworks.json", "nobroker.json", "gong.json", "plaid.json", "renaissancetech.json"]


def test_unknown_set_value_exits_2_without_scoring(capsys):
    assert main(["--set", "v3"]) == 2
    assert "--set takes v1" in capsys.readouterr().out


def test_real_v2_labels_are_eight_sites_with_urls_and_all_fifteen_fields():
    sites = v2_sites()
    assert [lf for lf, _, _ in sites] == [
        "cashfree.json", "chargebee.json", "cohere.json", "elevenlabs.json", "framer.json",
        "leadsquared.json", "mercury.json", "miro.json"]
    from eval.held_out import V2_LABEL_DIR
    for label_file, url, candidates in sites:
        doc = json.loads((V2_LABEL_DIR / label_file).read_text(encoding="utf-8"))
        assert url == doc["labeling_metadata"]["website_url"] and url.startswith("https://")
        assert list(doc["fields"]) == list(FIELDS)
        assert candidates[1] == "www_" + candidates[0]


def test_run_file_candidates_follow_run_site_slug(tmp_path):
    _label(tmp_path, "alpha", "https://www.alpha.co.uk/")
    _label(tmp_path, "beta", "https://beta.io/")
    assert v2_sites(tmp_path) == [("alpha.json", "https://www.alpha.co.uk/", ["alpha_co_uk", "www_alpha_co_uk"]),
                                  ("beta.json", "https://beta.io/", ["beta_io", "www_beta_io"])]


def test_v2_refuses_when_checksum_file_is_missing(tmp_path, monkeypatch, capsys):
    label_dir, run_dir, sums, report = _dirs(tmp_path, monkeypatch)
    _label(label_dir, "alpha", "https://alpha.com/")
    _run(run_dir, "alpha_com", [])
    monkeypatch.setattr("eval.held_out.run_scoring_set", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scored")))
    assert main_v2([], label_dir, sums, run_dir, report) == 1
    out = capsys.readouterr().out
    assert "https://alpha.com/" in out and "REFUSED" in out and "labels_v2.sha256 does not exist" in out
    assert not report.exists()


def test_v2_refuses_when_a_label_changed_after_the_checksum(tmp_path, monkeypatch, capsys):
    label_dir, run_dir, sums, report = _dirs(tmp_path, monkeypatch)
    _label(label_dir, "alpha", "https://alpha.com/")
    assert write(label_dir, sums)[0]
    path = label_dir / "alpha.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert main_v2([], label_dir, sums, run_dir, report) == 1
    assert "REFUSED" in capsys.readouterr().out and not report.exists()


def test_v2_scores_all_fifteen_fields_including_not_found_and_list_items(tmp_path, monkeypatch):
    label_dir, run_dir, sums, report = _dirs(tmp_path, monkeypatch)
    _label(label_dir, "alpha", "https://www.alpha.com/", {
        "company_identity.name": {"status": "extracted", "value": "Alpha", "source_url": "https://www.alpha.com/",
                                  "evidence": "Alpha"},
        "products.names": {"status": "extracted", "value": ["One", "Two"],
                           "source_url": ["https://www.alpha.com/", "https://www.alpha.com/"],
                           "evidence": ["One", "Two"]},
    })
    _label(label_dir, "beta", "https://beta.io/", {
        "company_identity.name": {"status": "extracted", "value": "Beta", "source_url": "https://beta.io/",
                                  "evidence": "Beta"},
    })
    assert write(label_dir, sums)[0]
    _run(run_dir, "alpha_com", [_claim(1, "company_identity.name", "Alpha", "https://alpha.com/"),
                                _claim(2, "products.names", ["One", "Three"], "https://alpha.com/"),
                                _claim(3, "company_identity.headquarters", "Paris", "https://alpha.com/")])
    _run(run_dir, "beta_io", [_claim(1, "company_identity.name", "Beta", "https://beta.io/")])

    assert main_v2([], label_dir, sums, run_dir, report) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["held_out_v2_set"] == ["alpha", "beta"]
    alpha, beta = data["per_site"]["alpha"]["counts"], data["per_site"]["beta"]["counts"]
    assert sum(alpha.values()) == sum(beta.values()) == len(FIELDS) == 15
    assert (alpha["correct"], alpha["correct_partial"], alpha["unsupported"], alpha["correct_abstention"]) == (1, 1, 1, 12)
    assert (beta["correct"], beta["correct_abstention"]) == (1, 14)
    assert data["overall"]["total"] == 30
