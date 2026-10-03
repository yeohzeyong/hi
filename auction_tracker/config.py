"""Configuration loading and project paths."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def load_yaml(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default) if default is not None else {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or (copy.deepcopy(default) if default is not None else {})
