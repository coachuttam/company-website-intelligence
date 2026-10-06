"""Loads config.yaml. All caps and limits live in config, never in code."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> Dict[str, Any]:
    with open(path or ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
