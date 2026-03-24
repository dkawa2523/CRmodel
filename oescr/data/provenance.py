
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict


def file_sha256(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance_record(path: str | Path, kind: str) -> Dict[str, str]:
    path = Path(path)
    return {
        "kind": kind,
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
    }
