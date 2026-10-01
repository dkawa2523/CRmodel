"""Serialization of forward diagnostics and provenance for CLI workflows."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from ..io.yaml_loader import save_yaml
from .model import ForwardResult


def forward_diagnostics_payload(result: ForwardResult) -> Dict[str, Any]:
    zones = []
    for zone_index, diagnostics in enumerate(result.zone_diagnostics):
        zones.append(
            {
                "zone_index": zone_index,
                "eedf": asdict(diagnostics.eedf),
                "cr": asdict(diagnostics.cr),
                "reactions": diagnostics.reactions,
                "processes": diagnostics.processes,
                "state_balances": {
                    state_id: balance.as_dict()
                    for state_id, balance in diagnostics.state_balances.items()
                },
                "bands": diagnostics.bands,
            }
        )
    return {
        "quality": result.quality_report.as_dict(),
        "emission_basis": result.emission_basis,
        "emission_component_bases": result.emission_component_bases,
        "provenance": result.provenance,
        "zones": zones,
    }


def write_forward_diagnostics(result: ForwardResult, path: str | Path) -> None:
    save_yaml(forward_diagnostics_payload(result), path)
