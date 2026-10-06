"""eval/baseline.py's run_scoring_set(): focused on the --semantic-judge cost/benefit summary
added 2026-09-28 (Uttam asked for cost/benefit visibility wherever an LLM gets called). The
per-site/per-field/overall printing itself is exercised end-to-end by running the real script
against real dev-set/held-out data (see PROGRESS.md) -- this test only covers the new summary,
using a fake judge so it needs no network or API key."""
from __future__ import annotations

import json

from wi.extract.fields import FIELDS
from wi.schemas.claim import Claim, Coverage, Status

from eval.baseline import run_scoring_set


class _FakeJudge:
    """Mimics wi.extract.llm.OpenAIJudgeCompleter's public shape (the .judge() method plus the
    three usage attributes run_scoring_set() reads afterward) without any real OpenAI call."""

    def __init__(self, verdict: bool):
        self._verdict = verdict
        self.call_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def judge(self, label_text, system_text, field, model) -> bool:
        self.call_count += 1
        self.total_prompt_tokens += 50
        self.total_completion_tokens += 5
        return self._verdict


def _label_doc() -> dict:
    fields = {f: {"status": "not_found"} for f in FIELDS}
    fields["company_identity.description"] = {
        "status": "extracted",
        "value": "Project management software, without all the nonsense.",
    }
    return {"site": "https://example.com/", "fields": fields}


def _claims() -> list:
    return [Claim(
        claim_id="c:1", field="company_identity.description", status=Status.extracted,
        value="Software for managing projects, minus the unnecessary complexity.",
        source_url="https://example.com/", page_title="Example",
        evidence="Software for managing projects, minus the unnecessary complexity.",
        retrieved_at="2026-09-28",
    )]


def test_semantic_judge_summary_printed_and_counts_the_upgrade(tmp_path, capsys, monkeypatch):
    # run_scoring_set() reports the written path as relative to eval/baseline.py's own ROOT
    # (the real repo root normally) -- point that at tmp_path for this test so a test run file
    # under pytest's own tmp dir doesn't trip relative_to() against the real repo root.
    monkeypatch.setattr("eval.baseline.ROOT", tmp_path)
    label_dir, run_dir = tmp_path / "labels", tmp_path / "runs"
    label_dir.mkdir()
    run_dir.mkdir()
    (label_dir / "example.json").write_text(json.dumps(_label_doc()))
    (run_dir / "example_run.json").write_text(json.dumps({
        "claims": [c.model_dump(mode="json") for c in _claims()]
    }))

    judge = _FakeJudge(verdict=True)  # judge says: same substance, upgrade it
    report, exit_code = run_scoring_set(
        site_set=[("example.json", "example_run.json")],
        label_dir=label_dir, run_dir=run_dir, set_key="example",
        report_path=tmp_path / "report.json", per_field_heading="example",
        semantic_judge=judge, semantic_judge_model="gpt-4o-mini",
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Semantic judge (gpt-4o-mini): 1 call(s), 55 tokens" in out
    assert "upgraded 1 field(s) incorrect -> correct_semantic" in out

    assert report["semantic_judge"] == {
        "model": "gpt-4o-mini", "calls": 1, "prompt_tokens": 50, "completion_tokens": 5,
        "estimated_cost_usd": report["semantic_judge"]["estimated_cost_usd"],  # priced elsewhere
        "fields_upgraded_to_correct_semantic": 1,
    }


def test_no_semantic_judge_summary_when_judge_is_none(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("eval.baseline.ROOT", tmp_path)
    label_dir, run_dir = tmp_path / "labels", tmp_path / "runs"
    label_dir.mkdir()
    run_dir.mkdir()
    (label_dir / "example.json").write_text(json.dumps(_label_doc()))
    (run_dir / "example_run.json").write_text(json.dumps({
        "claims": [c.model_dump(mode="json") for c in _claims()]
    }))

    report, exit_code = run_scoring_set(
        site_set=[("example.json", "example_run.json")],
        label_dir=label_dir, run_dir=run_dir, set_key="example",
        report_path=tmp_path / "report.json", per_field_heading="example",
        semantic_judge=None, semantic_judge_model=None,
    )

    assert exit_code == 0
    assert "Semantic judge" not in capsys.readouterr().out
    assert report["semantic_judge"] is None
