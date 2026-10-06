"""Tests for wi.extract.llm.OpenAIChatCompleter -- specifically that it actually sends the
temperature setting to the API (decided 2026-09-24, see its docstring for the real
run-to-run variance bug this fixes). Never touches the network or needs a real API key: the
`openai.OpenAI` client is monkeypatched with a fake that just records what it was called
with, the same pattern wi/crawl/clean.py's tests use for trafilatura.

Also covers OpenAIJudgeCompleter (B-45, 2026-09-27) with the same never-touch-the-network pattern.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from wi.extract.llm import OpenAIChatCompleter, OpenAIJudgeCompleter


class _FakeCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"claims": []}'))],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class _FakeOpenAIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def test_default_temperature_is_low_not_the_api_default(monkeypatch):
    # Before this fix, no temperature was sent at all, so the API silently used its own
    # default (1.0) -- a real source of the run-to-run variance seen live today.
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAIClient)
    completer = OpenAIChatCompleter(api_key="fake-key")
    completer.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o-mini")

    sent = completer._client.chat.completions.last_kwargs
    assert sent["temperature"] == 0.1


def test_temperature_is_configurable(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAIClient)
    completer = OpenAIChatCompleter(api_key="fake-key", temperature=0.0)
    completer.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o-mini")

    sent = completer._client.chat.completions.last_kwargs
    assert sent["temperature"] == 0.0


def test_complete_still_returns_usage_and_content_correctly(monkeypatch):
    # Sanity check that adding temperature didn't disturb the existing return-value mapping.
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAIClient)
    completer = OpenAIChatCompleter(api_key="fake-key")
    result = completer.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o-mini")

    assert result.content == '{"claims": []}'
    assert result.model == "gpt-4o-mini"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15


# ---------------------------------------------------------------------------
# OpenAIJudgeCompleter (B-45)
# ---------------------------------------------------------------------------

class _FakeJudgeCompletions:
    def __init__(self, same_substance: bool):
        self._same_substance = same_substance
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        content = json.dumps({"same_substance": self._same_substance, "reason": "because"})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=3, total_tokens=23),
        )


class _FakeJudgeOpenAIClient:
    def __init__(self, api_key=None, same_substance=True):
        self.api_key = api_key
        self.chat = SimpleNamespace(completions=_FakeJudgeCompletions(same_substance))


def test_judge_returns_true_when_the_model_says_same_substance(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, True))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    assert judge.judge("Helps teams manage social media.",
                        "A tool for managing your team's social media.",
                        "company_identity.description", model="gpt-4o-mini") is True


def test_judge_returns_false_when_the_model_says_different_substance(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, False))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    assert judge.judge("Helps teams manage social media.", "A payments platform.",
                        "company_identity.description", model="gpt-4o-mini") is False


def test_judge_defaults_to_zero_temperature(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, True))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    judge.judge("a", "b", "company_identity.description", model="gpt-4o-mini")
    assert judge._client.chat.completions.last_kwargs["temperature"] == 0.0


def test_judge_prompt_distinguishes_elaboration_from_material_fact(monkeypatch):
    # B-46: the first live --semantic-judge run showed the judge rejecting every one of 9
    # products.delivery_model candidates, including a couple that read as the same claim with a
    # same-category elaboration (see wi/eval/scoring.py's docstring). This locks in that the
    # revised prompt actually carries the worked examples meant to fix that, rather than testing
    # live model behaviour this sandbox has no network/API key to exercise.
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, True))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    judge.judge("a", "b", "products.delivery_model", model="gpt-4o-mini")
    system_content = judge._client.chat.completions.last_kwargs["messages"][0]["content"]
    assert "elaborates on the same underlying claim" in system_content
    assert "software" in system_content and "hardware devices" in system_content


def test_judge_sends_the_field_and_both_answers_to_the_model(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, True))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    judge.judge("label text", "system text", "products.delivery_model", model="gpt-4o-mini")
    sent = judge._client.chat.completions.last_kwargs
    user_content = sent["messages"][-1]["content"]
    assert "label text" in user_content
    assert "system text" in user_content
    assert "products.delivery_model" in user_content
    assert sent["model"] == "gpt-4o-mini"


def test_judge_accumulates_usage_across_calls(monkeypatch):
    # Added 2026-09-28 (cost/benefit visibility): eval/baseline.py's run_scoring_set() reads
    # these three attributes after scoring every site to print a cost summary for a
    # --semantic-judge run -- must accumulate across calls, not just hold the last one's numbers.
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _FakeJudgeOpenAIClient(api_key, True))
    judge = OpenAIJudgeCompleter(api_key="fake-key")
    assert (judge.call_count, judge.total_prompt_tokens, judge.total_completion_tokens) == (0, 0, 0)
    judge.judge("a", "b", "customers.segments", model="gpt-4o-mini")
    judge.judge("c", "d", "pricing.sales_motion", model="gpt-4o-mini")
    assert judge.call_count == 2
    assert judge.total_prompt_tokens == 40      # 20 per call, from _FakeJudgeCompletions
    assert judge.total_completion_tokens == 6   # 3 per call
