"""YAML loading helpers.

This module now does more than plain ``yaml.safe_load``.
It provides:

- recursive ``include`` support with deep merge
- relative-path rebasing for included fragments
- lightweight variable expansion for ``${THIS_DIR}``
- preservation of ``__base_dir__`` and ``__path__`` metadata for downstream
  path resolution

The goal is to keep user-facing YAML compact while keeping the internal model
configuration fully explicit and reproducible.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, overload

import yaml

_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _coerce_scalar(value: Any) -> Any:
    if isinstance(value, str) and _NUMERIC_RE.match(value.strip()):
        s = value.strip()
        try:
            if any(ch in s for ch in ".eE"):
                return float(s)
            return int(s)
        except ValueError:
            return value
    return value


def _coerce_numeric_scalars(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _coerce_numeric_scalars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_numeric_scalars(v) for v in obj]
    return _coerce_scalar(obj)



_PATH_KEYS = {
    "file",
    "files",
    "yaml_file",
    "window_registry",
    "profile_file",
    "cross_section_file",
    "case",
    "inverse",
    "project",
    "measurement_file",
    "measurement_files",
}
_PATH_SUFFIXES = ("_file", "_files", "_path", "_yaml", "_yaml_file", "_registry")
_PATH_EXTENSIONS = {".yaml", ".yml", ".csv", ".json", ".txt", ".md", ".toml"}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = deepcopy(base)
        for key, value in override.items():
            if key in out:
                out[key] = _deep_merge(out[key], value)
            else:
                out[key] = deepcopy(value)
        return out
    return deepcopy(override)


def _looks_like_relative_path(value: str) -> bool:
    if not value or value.startswith("${"):
        return False
    p = Path(value)
    if p.is_absolute():
        return False
    if "://" in value:
        return False
    if value.startswith("#"):
        return False
    return p.suffix.lower() in _PATH_EXTENSIONS or "/" in value or "\\" in value


def _should_rebase(key: str | None, value: str) -> bool:
    if key is not None and (key in _PATH_KEYS or key.endswith(_PATH_SUFFIXES)):
        return _looks_like_relative_path(value)
    return False


def _rebase_string_path(value: str, from_base: Path, to_base: Path) -> str:
    src = (from_base / value).resolve()
    try:
        return str(src.relative_to(to_base.resolve()))
    except ValueError:
        import os
        return os.path.relpath(src, start=to_base.resolve())


def _rebase_relative_paths(obj: Any, from_base: Path, to_base: Path, key: str | None = None) -> Any:
    if isinstance(obj, dict):
        return {
            k: _rebase_relative_paths(v, from_base=from_base, to_base=to_base, key=str(k))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        if key in {"files", "measurement_files"}:
            return [
                _rebase_relative_paths(v, from_base=from_base, to_base=to_base, key="file")
                for v in obj
            ]
        return [_rebase_relative_paths(v, from_base=from_base, to_base=to_base, key=key) for v in obj]
    if isinstance(obj, str) and _should_rebase(key, obj):
        return _rebase_string_path(obj, from_base=from_base, to_base=to_base)
    return obj


def _expand_string_variables(value: str, base_dir: Path) -> str:
    return value.replace("${THIS_DIR}", str(base_dir.resolve()))


def _expand_variables(obj: Any, base_dir: Path) -> Any:
    if isinstance(obj, dict):
        return {k: _expand_variables(v, base_dir) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_variables(v, base_dir) for v in obj]
    if isinstance(obj, str):
        return _expand_string_variables(obj, base_dir)
    return obj


def _normalize_include_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(v) for v in value]
    raise TypeError("'include' must be a string or a list of strings.")


def _load_yaml_internal(path: Path, stack: tuple[Path, ...] = ()) -> Dict[str, Any]:
    resolved = path.resolve()
    if resolved in stack:
        cycle = " -> ".join(str(p) for p in (*stack, resolved))
        raise ValueError(f"YAML include cycle detected: {cycle}")

    with resolved.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Top-level YAML document must be a mapping: {resolved}")

    base_dir = resolved.parent
    include_paths = _normalize_include_list(raw.pop("include", None))

    merged: Dict[str, Any] = {}
    for inc in include_paths:
        inc_path = (base_dir / inc).resolve()
        inc_data = _load_yaml_internal(inc_path, stack=(*stack, resolved))
        inc_clean = deepcopy(inc_data)
        inc_clean.pop("__base_dir__", None)
        inc_clean.pop("__path__", None)
        inc_clean = _rebase_relative_paths(inc_clean, from_base=inc_path.parent, to_base=base_dir)
        merged = _deep_merge(merged, inc_clean)

    merged = _deep_merge(merged, raw)
    merged = _expand_variables(merged, base_dir)
    merged = _coerce_numeric_scalars(merged)
    merged["__base_dir__"] = str(base_dir.resolve())
    merged["__path__"] = str(resolved)
    return merged


def load_yaml(path: str | Path) -> Dict[str, Any]:
    """Load YAML with include support.

    The returned mapping contains:

    - ``__base_dir__``: absolute directory of the root YAML
    - ``__path__``: absolute path of the root YAML
    """

    return _load_yaml_internal(Path(path))


def save_yaml(data: Dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = deepcopy(data)
    clean.pop("__base_dir__", None)
    clean.pop("__path__", None)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(clean, f, sort_keys=False)


@overload
def resolve_path(config: Mapping[str, Any], path_str: str) -> Path:
    ...


@overload
def resolve_path(config: Mapping[str, Any], path_str: None) -> None:
    ...


def resolve_path(config: Mapping[str, Any], path_str: str | None) -> Path | None:
    if path_str is None:
        return None
    p = Path(path_str)
    if p.is_absolute():
        return p
    base = Path(config.get("__base_dir__", "."))
    return (base / p).resolve()
