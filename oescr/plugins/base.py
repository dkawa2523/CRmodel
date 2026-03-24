from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any, Dict, Generic, Mapping, MutableMapping, TypeVar

from jsonschema import Draft202012Validator


class PluginConfigError(ValueError):
    """Raised when a plugin receives an invalid configuration payload."""


class PluginBase(ABC):
    """Base class for pluggable submodels.

    Each plugin owns a *kind* string, an optional JSON Schema fragment for structural
    validation, and a human-readable description. The runtime registries use these
    contracts to validate configuration objects before simulation code is executed.
    """

    kind: str = ""
    description: str = ""
    config_schema: Mapping[str, Any] | None = None

    def validate_config(self, cfg: Mapping[str, Any]) -> None:
        schema = self.config_schema
        if schema is not None:
            validator = Draft202012Validator(schema)
            errors = sorted(validator.iter_errors(dict(cfg)), key=lambda e: list(e.absolute_path))
            if errors:
                top = errors[0]
                path = ".".join(str(p) for p in top.absolute_path) or "<root>"
                raise PluginConfigError(f"Plugin '{self.kind}' config invalid at {path}: {top.message}")
        self._validate_semantics(cfg)

    def _validate_semantics(self, cfg: Mapping[str, Any]) -> None:
        return None

    def catalog_entry(self) -> Dict[str, Any]:
        return {"kind": self.kind, "description": self.description}


P = TypeVar("P", bound=PluginBase)


@dataclass
class PluginRegistry(Generic[P]):
    name: str

    def __post_init__(self) -> None:
        self._plugins: MutableMapping[str, P] = {}

    def register(self, plugin: P, *, replace: bool = False) -> P:
        kind = str(plugin.kind)
        if not kind:
            raise ValueError(f"Cannot register unnamed plugin in registry '{self.name}'.")
        if kind in self._plugins and not replace:
            raise ValueError(f"Plugin kind '{kind}' already registered in '{self.name}'.")
        self._plugins[kind] = plugin
        return plugin

    def get(self, kind: str) -> P:
        try:
            return self._plugins[str(kind)]
        except KeyError as exc:
            known = ", ".join(sorted(self._plugins))
            raise KeyError(f"Unknown plugin kind '{kind}' for registry '{self.name}'. Known: {known}") from exc

    def validate(self, kind: str, cfg: Mapping[str, Any]) -> None:
        self.get(kind).validate_config(cfg)

    def list_kinds(self) -> list[str]:
        return sorted(self._plugins)

    def catalog(self) -> Dict[str, Dict[str, Any]]:
        return {kind: plugin.catalog_entry() for kind, plugin in sorted(self._plugins.items())}
