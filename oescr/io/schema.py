"""JSON Schema validation for user-facing YAML documents.

The package now performs two validation passes:

1. *Structural validation* via JSON Schema for user-facing YAML files.
2. *Semantic validation* via Python checks after normalization and plugin resolution.

The goal is to keep YAML authoring ergonomic while providing strict, machine-checkable
contracts for configuration layout.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
AVAILABLE_SCHEMAS = {
    "case": "case.schema.yaml",
    "inverse": "inverse.schema.yaml",
    "project": "project.schema.yaml",
    "instrument": "instrument.schema.yaml",
    "windows": "windows.schema.yaml",
    "validation": "validation.schema.yaml",
}


class ConfigSchemaError(ValueError):
    """Raised when a user-facing YAML document violates its structural schema."""


def _public_view(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _public_view(v) for k, v in obj.items() if not str(k).startswith("__")}
    if isinstance(obj, list):
        return [_public_view(v) for v in obj]
    return obj


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> Dict[str, Any]:
    try:
        filename = AVAILABLE_SCHEMAS[schema_name]
    except KeyError as exc:
        raise KeyError(f"Unknown schema name: {schema_name!r}. Available: {sorted(AVAILABLE_SCHEMAS)}") from exc
    path = SCHEMA_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def get_validator(schema_name: str) -> Draft202012Validator:
    schema = load_schema(schema_name)
    return Draft202012Validator(schema)


def _format_error(error: Any) -> str:
    path = ".".join(str(p) for p in error.absolute_path)
    location = path or "<root>"
    return f"{location}: {error.message}"


def validate_document(doc: Dict[str, Any], schema_name: str) -> None:
    public_doc = _public_view(doc)
    validator = get_validator(schema_name)
    errors = sorted(validator.iter_errors(public_doc), key=lambda e: list(e.absolute_path))
    if not errors:
        return

    top = errors[:8]
    detail = "\n  - ".join(_format_error(e) for e in top)
    more = "" if len(errors) <= len(top) else f"\n  ... {len(errors) - len(top)} more schema violations"
    raise ConfigSchemaError(
        f"{schema_name} YAML failed schema validation with {len(errors)} violation(s):\n  - {detail}{more}"
    )
