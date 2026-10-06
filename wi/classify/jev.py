"""Minimal client for TypeSafe's Jev "System One" API (POST /v1/systemone).

Jev returns typed decisions with probabilities (a choice among named options, an ordered score,
or a yes/no probability) instead of text. Request and response shapes below were confirmed with a
real call on 2026-10-06 (eval/jev_smoke.py): the body needs "model", "state" and "questions";
the response has "model", "answers" (one entry per question id) and "usage". A body without
"model" is rejected with HTTP 422.

The API key is read from the environment (JEV_API_KEY, normally set through the git-ignored
.env) and is never logged, printed or placed in an error message.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"


class JevError(Exception):
    """Any failure to get a usable answer from Jev (missing key, network, HTTP error, bad body)."""


@dataclass
class JevResult:
    model: str
    answers: Dict[str, Dict[str, Any]]
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0


@dataclass
class JevClient:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = 30.0
    client: Optional[httpx.Client] = None   # injectable, so tests never touch the network

    @classmethod
    def from_env(cls, classifier_cfg: Optional[dict] = None) -> "JevClient":
        cfg = (classifier_cfg or {}).get("jev", {}) if classifier_cfg else {}
        key = os.environ.get("JEV_API_KEY", "").strip()
        if not key:
            raise JevError("JEV_API_KEY is not set (add it to .env)")
        return cls(
            api_key=key,
            base_url=os.environ.get("JEV_BASE_URL", "").strip() or cfg.get("base_url", DEFAULT_URL),
            model=os.environ.get("JEV_MODEL", "").strip() or cfg.get("model", DEFAULT_MODEL),
            timeout_s=float(cfg.get("timeout_s", 30)),
        )

    def evaluate(self, state: str, questions: Dict[str, dict]) -> JevResult:
        body = {"model": self.model, "state": state, "questions": questions}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        start = time.monotonic()
        try:
            if self.client is not None:
                resp = self.client.post(self.base_url, json=body, headers=headers)
            else:
                resp = httpx.post(self.base_url, json=body, headers=headers, timeout=self.timeout_s)
        except httpx.HTTPError as e:
            raise JevError(f"request failed: {type(e).__name__}") from e
        elapsed = time.monotonic() - start
        if resp.status_code != 200:
            raise JevError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            answers = data["answers"]
        except (ValueError, KeyError, TypeError) as e:
            raise JevError("response was not the expected JSON with an 'answers' object") from e
        usage = data.get("usage") or {}
        return JevResult(
            model=str(data.get("model", self.model)),
            answers=answers,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            elapsed_s=elapsed,
        )
