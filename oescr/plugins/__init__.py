"""Shared plugin infrastructure used by physical and instrument submodels."""

from .base import PluginBase, PluginConfigError, PluginRegistry

__all__ = ["PluginBase", "PluginConfigError", "PluginRegistry"]
