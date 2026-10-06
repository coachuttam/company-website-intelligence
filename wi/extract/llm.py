"""The one place that talks to the LLM provider (PRD Section 9, Rule 5: log
tokens, latency and cost from the first call). `ChatCompleter` is a small
Protocol so wi/extract/pipeline.py never imports the openai package directly --
tests inject a fake completer and never touch the network or need an API key.

Cost: config.yaml's targets (cost_mean_usd, cost_p95_usd) are what a run is
judged against, but this module does not compute an actual dollar figure --
that needs a $/token price table for whichever model is configured, which
doesn't exist anywhere in the project yet. Token counts are captured now so
that table can be added later without re-running anything; treat the "cost"
column as not yet wired up rather than silently zero.

`JudgeCompleter`/`OpenAIJudgeCompleter` (B-45, 2026-09-27): a second, deliberately separate
Protocol+implementation pair for wi.eval.scoring's opt-in semantic-equivalence check (see that
module's docstring). Kept apart from ChatCompleter/OpenAIChatCompleter above rather than reusing
them: `OpenAIChatCompleter.complete()` hardcodes its response_format to CLAIMS_RESPONSE_SCHEMA
(the 15-field extraction shape), which has nothing to do with a yes/no judgment between two short
answers, and forcing the judge call through that schema would mean either breaking extraction's
contract or a bigger refactor than this narrow, opt-in feature needs. Same lazy `openai` import
and same "tests inject a fake, never touch the network" pattern as ChatCompleter.

B-46 (2026-09-27) prompt revision: the first live `--semantic-judge` run showed the judge
declining to upgrade every one of 9 candidate products.delivery_model verdicts, including a couple
that looked, on manual inspection, like the same core claim with a same-category elaboration (e.g.
label "software (API/developer platform)" vs system "software") -- exactly the case the original
prompt's "a vaguer or more general phrasing... still counts" sentence was meant to cover, just
without a concrete enough rule for the model to apply it consistently. The system prompt below adds
a worked example of each side of the elaboration/material-fact line instead of leaving "material
fact" undefined. This is a wording change only, unverified from this codebase's own test suite or
this sandbox (no network/API key here) -- confirming it actually moves live judge behaviour needs a
real `--semantic-judge` re-run.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import List, Protocol

from wi.extract.schema import CLAIMS_RESPONSE_SCHEMA

JUDGE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "same_substance": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["same_substance", "reason"],
    "additionalProperties": False,
}


@dataclass
class LLMResult:
    content: str            # raw JSON text: {"claims": [...]}
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    elapsed_s: float


class ChatCompleter(Protocol):
    def complete(self, messages: List[dict], model: str) -> LLMResult: ...


class OpenAIChatCompleter:
    """Real implementation. Needs OPENAI_API_KEY in the environment (.env).

    `temperature` (decided 2026-09-24): the API call previously never set this, so every run
    used OpenAI's default (1.0) -- a real, measured contributor to today's run-to-run
    variance. Across live basecamp.com runs the same field flipped between succeeding and
    failing from one run to the next with nothing else changed (pricing.public_plans alone
    swung from a correct array-evidence claim to a fabricated combined quote and back several
    times). Defaults to 0.1 here: low enough to make the model's choice of quote and status
    far more repeatable run to run, not 0.0, since some legitimate variation in phrasing is
    fine and a hard-zero temperature can make some providers behave oddly on structured
    output. Configurable via config.yaml's llm.temperature so it can be tuned without a
    code change.
    """

    def __init__(self, api_key: str, temperature: float = 0.1):
        from openai import OpenAI  # imported lazily so tests never need the package installed
        self._client = OpenAI(api_key=api_key)
        self._temperature = temperature

    def complete(self, messages: List[dict], model: str) -> LLMResult:
        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=self._temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "claims", "schema": CLAIMS_RESPONSE_SCHEMA, "strict": True},
            },
        )
        elapsed = time.monotonic() - start
        choice = response.choices[0]
        usage = response.usage
        return LLMResult(
            content=choice.message.content,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            elapsed_s=elapsed,
        )


class JudgeCompleter(Protocol):
    def judge(self, label_text: str, system_text: str, field: str, model: str) -> bool: ...


class OpenAIJudgeCompleter:
    """Real implementation of the B-45 semantic-equivalence judge (see this module's and
    wi.eval.scoring's docstrings). Needs OPENAI_API_KEY in the environment, same as
    OpenAIChatCompleter. `temperature` defaults to 0.0 (not 0.1 like extraction) -- a judge call
    is a factual yes/no comparison, not a creative-quote-selection task, so there's no reason to
    want run-to-run variation here the way OpenAIChatCompleter's docstring explains wanting a
    little for extraction."""

    def __init__(self, api_key: str, temperature: float = 0.0):
        from openai import OpenAI  # imported lazily, same reason as OpenAIChatCompleter
        self._client = OpenAI(api_key=api_key)
        self._temperature = temperature
        # Added 2026-09-28 (Uttam asked for cost/benefit visibility everywhere an LLM gets
        # called, not just the main extraction call): every judge() call below was making a
        # real, billed OpenAI request whose tokens were read off `response.usage` and then
        # immediately thrown away -- there was no way to know how many judge calls a
        # `--semantic-judge` run made or what they cost. Accumulated here rather than
        # returned per-call so callers (eval/baseline.py's run_scoring_set(), reused by
        # held_out.py and score_one.py) can read one running total after scoring every site,
        # instead of threading a usage value through every judge() call site.
        self.call_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def judge(self, label_text: str, system_text: str, field: str, model: str) -> bool:
        messages = [
            {"role": "system", "content": (
                "You are checking whether two short answers to the same question state the same "
                "substantive facts, ignoring differences in wording, length, phrasing, or "
                "specificity. A vaguer or more general phrasing of the exact same claim still "
                "counts as the same substance -- do not require identical wording, and do not "
                "penalise the shorter answer just for omitting descriptive detail that elaborates "
                "on the same underlying claim. For example, 'software' and 'a cloud-based "
                "software platform, accessed via web app and mobile apps' are the SAME substance "
                "-- the longer answer just names the channel/format of the same claim, it does "
                "not add a new one. Only mark them different when one answer includes a REAL "
                "material fact the other omits or contradicts: a fact that would change what the "
                "reader concludes, such as an entirely separate offering, capability, or "
                "deployment mode the shorter answer gives no indication of. For example, "
                "'software' and 'software, and the company also sells physical hardware devices' "
                "are DIFFERENT substance -- the hardware line is not implied by 'software' at "
                "all. Do not reward an answer that merely sounds plausible if it actually changes "
                "the meaning."
            )},
            {"role": "user", "content": (
                f"Field: {field}\n\nAnswer A (reference): {label_text}\n\n"
                f"Answer B (system): {system_text}\n\n"
                "Do A and B state the same substantive facts?"
            )},
        ]
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=self._temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "judge", "schema": JUDGE_RESPONSE_SCHEMA, "strict": True},
            },
        )
        usage = response.usage
        self.call_count += 1
        self.total_prompt_tokens += usage.prompt_tokens if usage else 0
        self.total_completion_tokens += usage.completion_tokens if usage else 0
        parsed = json.loads(response.choices[0].message.content)
        return bool(parsed["same_substance"])
