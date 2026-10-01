"""Composition of reusable OESCR emitter/species fragments.

Species packs group spectroscopic states and reduced-CR processes. They do not
solve gas composition or introduce a global chemistry model.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

from .yaml_loader import load_yaml, resolve_path

_SECTIONS = ("states", "reactions", "transitions", "quenching", "losses", "bands")
_PATH_KEYS = {"cross_section_file", "profile_file"}


class SpeciesPackError(ValueError):
    pass


def _namespace_id(namespace: str, value: str) -> str:
    if not namespace or ":" in value:
        return value
    return f"{namespace}:{value}"


def _resolve_pack_paths(value: Any, pack_cfg: Mapping[str, Any], key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {name: _resolve_pack_paths(item, pack_cfg, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_resolve_pack_paths(item, pack_cfg, key) for item in value]
    if key in _PATH_KEYS and isinstance(value, str):
        return str(resolve_path(pack_cfg, value))
    return deepcopy(value)


def _apply_namespace(pack_cfg: Dict[str, Any], namespace: str) -> Dict[str, Any]:
    out = deepcopy(pack_cfg)
    local_states = {str(item["id"]) for item in out.get("states", [])}
    state_map = {state_id: _namespace_id(namespace, state_id) for state_id in local_states}

    for state in out.get("states", []):
        state["id"] = state_map[str(state["id"])]
    for reaction in out.get("reactions", []):
        reaction["id"] = _namespace_id(namespace, str(reaction["id"]))
        for key in ("source_state", "target_state"):
            if str(reaction.get(key)) in state_map:
                reaction[key] = state_map[str(reaction[key])]
        reaction["colliders"] = [state_map.get(str(item), str(item)) for item in reaction.get("colliders", [])]
    for transition in out.get("transitions", []):
        if "id" in transition:
            transition["id"] = _namespace_id(namespace, str(transition["id"]))
        for key in ("upper", "lower"):
            if str(transition.get(key)) in state_map:
                transition[key] = state_map[str(transition[key])]
    for quenching in out.get("quenching", []):
        if str(quenching.get("state")) in state_map:
            quenching["state"] = state_map[str(quenching["state"])]
        if str(quenching.get("collider")) in state_map:
            quenching["collider"] = state_map[str(quenching["collider"])]
    for loss in out.get("losses", []):
        if str(loss.get("state")) in state_map:
            loss["state"] = state_map[str(loss["state"])]
    for band in out.get("bands", []):
        band["id"] = _namespace_id(namespace, str(band["id"]))
        source_key = str(band.get("source_density_key", ""))
        if source_key in state_map:
            band["source_density_key"] = state_map[source_key]
    return out


def _append_unique(target: list[Dict[str, Any]], additions: list[Dict[str, Any]], section: str) -> None:
    existing = {str(item["id"]) for item in target if "id" in item}
    for item in additions:
        item_id = str(item["id"]) if "id" in item else None
        if item_id is not None and item_id in existing:
            raise SpeciesPackError(f"Duplicate {section} id while composing species packs: {item_id}")
        target.append(deepcopy(item))
        if item_id is not None:
            existing.add(item_id)


def compose_species_packs(cfg: Dict[str, Any]) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    """Expand species_packs into ordinary case sections and return provenance."""

    out = deepcopy(cfg)
    pack_entries = list(out.pop("species_packs", []))
    provenance: list[Dict[str, Any]] = []
    for section in _SECTIONS:
        out.setdefault(section, [])

    for index, entry in enumerate(pack_entries):
        if not isinstance(entry, dict):
            raise SpeciesPackError(f"species_packs[{index}] must be a mapping.")
        if "yaml_file" in entry:
            pack_path = resolve_path(cfg, str(entry["yaml_file"]))
            pack_cfg = load_yaml(pack_path)
            source = str(Path(pack_path).resolve())
        else:
            pack_cfg = deepcopy(entry)
            pack_cfg.setdefault("__base_dir__", cfg.get("__base_dir__", "."))
            source = "<inline>"

        kind = str(pack_cfg.get("kind", "oescr_species_pack"))
        if kind != "oescr_species_pack":
            raise SpeciesPackError(f"Unsupported species pack kind: {kind}")
        namespace = str(entry.get("namespace", pack_cfg.get("namespace", ""))).strip()
        pack_cfg = _resolve_pack_paths(pack_cfg, pack_cfg)
        pack_cfg = _apply_namespace(pack_cfg, namespace)

        for section in _SECTIONS:
            _append_unique(out[section], list(pack_cfg.get(section, [])), section)

        provenance.append(
            {
                "source": source,
                "namespace": namespace,
                "metadata": deepcopy(pack_cfg.get("metadata", {})),
            }
        )

    return out, provenance
