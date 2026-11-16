"""Load a company config (YAML). The only place company-specific facts enter the code."""
from pathlib import Path
import yaml


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "company" not in cfg:
        raise ValueError(f"{path}: config must define 'company'")
    return cfg
