"""Validation against the shared JSON Schemas in contracts/schemas/."""

import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from .config import SCHEMAS


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def errors(obj: dict, name: str) -> list[str]:
    """name: "analysis_result" | "eval_summary" | "photo_record". Empty list when valid."""
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in _validator(name).iter_errors(obj)]


def validate(obj: dict, name: str) -> dict:
    errs = errors(obj, name)
    if errs:
        raise ValueError(f"invalid {name}: " + "; ".join(errs[:5]))
    return obj
