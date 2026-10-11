"""B-101: eval/dev13_summary.py parsing, headlines and pass test. Fixture files only, no model call."""
from __future__ import annotations

import json

from eval.dev13_summary import headlines, load, main, pass_test, verdict_totals

FIELDS = ["company_identity.name", "traction.partnerships"]


def _report(total, right, unsupported=0, incorrect=0, norm_extra=0, field_bad=0):
    counts = {"correct": right, "incorrect": incorrect, "correct_abstention": 0,
              "miss": total - right - unsupported - incorrect, "unsupported": unsupported, "conflicting": 0,
              "correct_partial": 0, "correct_semantic": 0}
    per_field = {FIELDS[0]: {"counts": {"incorrect": 0, "unsupported": 0}},
                 FIELDS[1]: {"counts": {"incorrect": field_bad, "unsupported": 0}}}
    return {"overall": {"total": total, "counts": counts}, "per_field": per_field,
            "normalised": {"right_calls": right + norm_extra}}


def _write(tmp, ref, rnd, dev5, v2, total_s=(80.0, 90.0)):
    (tmp / f"{ref}_r{rnd}_dev5.json").write_text(json.dumps(dev5))
    (tmp / f"{ref}_r{rnd}_v2.json").write_text(json.dumps(v2))
    runs = tmp / f"{ref}_r{rnd}_runs"
    runs.mkdir()
    for i, t in enumerate(total_s):
        (runs / f"s{i}.json").write_text(json.dumps({"timing": {"total_s": t}}))


def test_load_and_headlines(tmp_path):
    _write(tmp_path, "main", 1, _report(75, 48, norm_extra=3), _report(120, 42, norm_extra=13))
    (tmp_path / "main_r2_dev5.json").write_text(json.dumps(_report(75, 50)))   # incomplete round: ignored
    data = load(tmp_path)
    assert list(data) == ["main"] and list(data["main"]) == [1]
    h = headlines(data["main"][1])
    assert h["n"] == 195 and round(h["dev5"][0], 1) == 64.0 and round(h["v2"][0], 1) == 35.0
    assert round(h["combined"][0], 1) == round(100 * 90 / 195, 1) and round(h["combined"][1], 1) == round(100 * 106 / 195, 1)


def test_pass_test_each_rule(tmp_path):
    ctl = {1: {"dev5": _report(75, 48, unsupported=5), "v2": _report(120, 42, unsupported=4)}}
    good = {1: {"dev5": _report(75, 50, unsupported=6), "v2": _report(120, 43, unsupported=5)}}   # +3 right, +2 unsupported
    assert pass_test(ctl, good) == {"headline": True, "unsupported": True, "no_field_regression": True, "overall": True}
    flat = {1: {"dev5": _report(75, 48), "v2": _report(120, 43)}}                                  # +1 right = +0.5 point
    assert pass_test(ctl, flat)["headline"] is False
    noisy = {1: {"dev5": _report(75, 52, unsupported=10), "v2": _report(120, 44, unsupported=3)}}  # +4 unsupported
    assert pass_test(ctl, noisy)["unsupported"] is False and pass_test(ctl, noisy)["overall"] is False
    regress = {1: {"dev5": _report(75, 52, field_bad=4), "v2": _report(120, 44)}}                 # one field +4 incorrect
    assert pass_test(ctl, regress)["no_field_regression"] is False
    assert verdict_totals(good)["unsupported"] == 11


def test_main_prints_summary_and_spread(tmp_path, capsys):
    _write(tmp_path, "main", 1, _report(75, 48), _report(120, 42))
    _write(tmp_path, "main", 2, _report(75, 50), _report(120, 41))
    _write(tmp_path, "cand", 1, _report(75, 52), _report(120, 45), total_s=(85.0, 95.0))
    _write(tmp_path, "cand", 2, _report(75, 51), _report(120, 46), total_s=(86.0, 96.0))
    assert main(["main", "cand", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "control round-to-round spread" in out and "cand: headline +1.0 PASS" in out
    assert "p50" in out and main(["main", "nope", "--dir", str(tmp_path)]) == 1
