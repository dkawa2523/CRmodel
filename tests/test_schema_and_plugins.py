from __future__ import annotations

from pathlib import Path

from oescr.api import EEDF_PLUGINS, GEOMETRY_PLUGINS, REACTION_RATE_PLUGINS, validate_document
from oescr.io.yaml_loader import load_yaml
from oescr.plugins.base import PluginRegistry, PluginBase


ROOT = Path(__file__).resolve().parents[1]


def test_example_yaml_passes_structural_schema() -> None:
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    inv_cfg = load_yaml(ROOT / "examples" / "inverse_cf4_o2_ar.yaml")
    project_cfg = load_yaml(ROOT / "examples" / "project_cf4_o2_ar.yaml")
    inst_cfg = load_yaml(ROOT / "examples" / "instruments" / "uvvis_lowres.yaml")
    win_cfg = load_yaml(ROOT / "examples" / "diagnostics" / "windows.yaml")

    validate_document(case_cfg, "case")
    validate_document(inv_cfg, "inverse")
    validate_document(project_cfg, "project")
    validate_document(inst_cfg, "instrument")
    validate_document(win_cfg, "windows")


def test_builtin_plugin_catalogs_are_populated() -> None:
    assert "te_maxwell" in EEDF_PLUGINS.list_kinds()
    assert "cross_section_file" in REACTION_RATE_PLUGINS.list_kinds()
    assert "axisym_shell" in GEOMETRY_PLUGINS.list_kinds()


class _DummyPlugin(PluginBase):
    kind = "dummy"
    description = "test plugin"



def test_plugin_registry_supports_third_party_registration() -> None:
    reg: PluginRegistry[_DummyPlugin] = PluginRegistry("dummy_registry")
    reg.register(_DummyPlugin())
    assert reg.get("dummy").description == "test plugin"
