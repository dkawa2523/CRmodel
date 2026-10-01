
from __future__ import annotations

import re
from typing import Any, List

_TOKEN_RE = re.compile(r"([^.\[]+)(?:\[(\d+)\])?")


def _parse_path(path: str) -> List[Any]:
    tokens: List[Any] = []
    for chunk in path.split("."):
        m = _TOKEN_RE.fullmatch(chunk)
        if not m:
            raise ValueError(f"Invalid path token: {chunk}")
        key, idx = m.group(1), m.group(2)
        tokens.append(key)
        if idx is not None:
            tokens.append(int(idx))
    return tokens


def get_path(data: Any, path: str) -> Any:
    obj = data
    for tok in _parse_path(path):
        obj = obj[tok]
    return obj


def set_path(data: Any, path: str, value: Any) -> Any:
    obj = data
    tokens = _parse_path(path)
    for tok in tokens[:-1]:
        obj = obj[tok]
    obj[tokens[-1]] = value
    return data
