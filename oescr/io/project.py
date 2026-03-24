from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .validators import validate_project_structural
from .yaml_loader import load_yaml, resolve_path


@dataclass
class ProjectManifest:
    raw: Dict[str, Any]
    path: Path
    case_yaml: Path
    inverse_yaml: Path | None
    default_output_dir: Path

    @property
    def name(self) -> str:
        return str(self.raw.get("project", {}).get("name", self.path.stem))


def load_project(path: str | Path) -> ProjectManifest:
    cfg = load_yaml(path)
    validate_project_structural(cfg)
    kind = cfg.get("kind", "oescr_project")
    if kind != "oescr_project":
        raise ValueError(f"Unsupported project manifest kind: {kind}")

    case_yaml = resolve_path(cfg, cfg.get("case"))
    if case_yaml is None:
        raise ValueError("Project manifest must define 'case'.")
    inverse_yaml = resolve_path(cfg, cfg.get("inverse")) if cfg.get("inverse") else None

    out_dir = resolve_path(cfg, cfg.get("outputs", {}).get("default_dir", "outputs"))
    assert out_dir is not None
    return ProjectManifest(
        raw=cfg,
        path=Path(path).resolve(),
        case_yaml=case_yaml,
        inverse_yaml=inverse_yaml,
        default_output_dir=out_dir,
    )
