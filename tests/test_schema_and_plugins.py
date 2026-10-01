from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from oescr.api import (
    EEDF_PLUGINS,
    GEOMETRY_PLUGINS,
    REACTION_RATE_PLUGINS,
    EEDFPlugin,
    validate_document,
)
from oescr.forward.model import OESCRModel
from oescr.geometry.plugin import GeometryPlugin
from oescr.inverse.optimize import InverseSolver
from oescr.io.validators import ConfigSemanticError, validate_case_config
from oescr.io.yaml_loader import load_yaml
from oescr.plugins.base import PluginBase, PluginRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_example_yaml_passes_structural_schema() -> None:
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    inv_cfg = load_yaml(ROOT / "examples" / "inverse_cf4_o2_ar.yaml")
    project_cfg = load_yaml(ROOT / "examples" / "project_cf4_o2_ar.yaml")
    inst_cfg = load_yaml(ROOT / "examples" / "instruments" / "uvvis_lowres.yaml")
    win_cfg = load_yaml(ROOT / "examples" / "diagnostics" / "windows.yaml")
    curated_win_cfg = load_yaml(
        ROOT / "examples" / "diagnostics" / "windows_ar_nf3_cl2_bcl3_curated.yaml"
    )
    extended_win_cfg = load_yaml(
        ROOT / "examples" / "diagnostics" / "windows_ar_nf3_cl2_bcl3_extended.yaml"
    )
    validation_cfg = load_yaml(
        ROOT / "examples" / "benchmarks" / "nf3_ar_ccp_clean_2023" / "validation.yaml"
    )

    validate_document(case_cfg, "case")
    validate_document(inv_cfg, "inverse")
    validate_document(project_cfg, "project")
    validate_document(inst_cfg, "instrument")
    validate_document(win_cfg, "windows")
    validate_document(curated_win_cfg, "windows")
    validate_document(extended_win_cfg, "windows")
    validate_document(validation_cfg, "validation")


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


class _SingleChordTestGeometry(GeometryPlugin):
    kind = "test_single_chord"
    description = "Test-only public YAML geometry plugin."
    config_schema = {
        "type": "object",
        "required": ["mode", "n_shells", "weight"],
        "properties": {
            "mode": {"const": "test_single_chord"},
            "n_shells": {"type": "integer", "minimum": 1},
            "weight": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    }

    def build_matrix(self, cfg):
        geom = cfg.get("geometry", cfg)
        return np.full((1, int(geom["n_shells"])), float(geom["weight"]))


def test_registered_geometry_plugin_runs_through_public_yaml_path() -> None:
    if _SingleChordTestGeometry.kind not in GEOMETRY_PLUGINS.list_kinds():
        GEOMETRY_PLUGINS.register(_SingleChordTestGeometry())
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    case_cfg["geometry"] = {
        "mode": _SingleChordTestGeometry.kind,
        "n_shells": 3,
        "weight": 1.0,
    }

    validate_document(case_cfg, "case")
    result = OESCRModel(case_cfg).predict()

    assert len(result.spectra["uvvis_lowres"]) == 1


def test_rate_model_envelope_runs_through_public_yaml_path() -> None:
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    case_cfg["reactions"][0].pop("cross_section_file")
    case_cfg["reactions"][0]["rate_model"] = {
        "kind": "constant",
        "coefficient_m3_s": 1.0e-15,
    }

    validate_document(case_cfg, "case")
    result = OESCRModel(case_cfg).predict()

    assert result.zone_populations


class _PublicEnvelopeEEDF(EEDFPlugin):
    kind = "test_public_envelope"
    description = "Test-only EEDF selected without plasma_mode."
    config_schema = {
        "type": "object",
        "required": ["kind", "scale_eV"],
        "properties": {
            "kind": {"const": "test_public_envelope"},
            "scale_eV": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def build_pdf(self, spec, energy_eV):
        pdf = np.sqrt(np.maximum(energy_eV, 0.0)) * np.exp(-energy_eV / float(spec["scale_eV"]))
        return pdf / np.trapezoid(pdf, energy_eV)


def test_registered_eedf_plugin_runs_through_public_yaml_envelope() -> None:
    if _PublicEnvelopeEEDF.kind not in EEDF_PLUGINS.list_kinds():
        EEDF_PLUGINS.register(_PublicEnvelopeEEDF())
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    case_cfg.pop("plasma_mode")
    case_cfg["plasma_state"].pop("te_shells_eV")
    case_cfg["eedf"] = {
        "kind": _PublicEnvelopeEEDF.kind,
        "zones": [{"scale_eV": value} for value in (2.1, 2.0, 1.7)],
    }

    validate_document(case_cfg, "case")
    result = OESCRModel(case_cfg).predict()

    assert len(result.zone_diagnostics) == 3
    assert all(zone.eedf.normalization == pytest.approx(1.0) for zone in result.zone_diagnostics)
    assert result.provenance["eedf_kind"] == _PublicEnvelopeEEDF.kind


def test_public_eedf_envelope_rejects_legacy_selector_and_wrong_zone_count() -> None:
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    case_cfg["eedf"] = {"kind": "te_maxwell", "zones": [{"te_eV": 2.0}] * 3}
    with pytest.raises(ConfigSemanticError, match="either the public eedf envelope"):
        validate_case_config(case_cfg)

    case_cfg.pop("plasma_mode")
    case_cfg["eedf"]["zones"] = [{"te_eV": 2.0}]
    with pytest.raises(ConfigSemanticError, match="eedf.zones length 1"):
        validate_case_config(case_cfg)


@pytest.mark.parametrize("constraint_kind", ["prior", "regularization"])
def test_inverse_rejects_constraints_on_fixed_values(constraint_kind: str) -> None:
    case_cfg = load_yaml(ROOT / "examples" / "case_init_cf4_o2_ar.yaml")
    inv_cfg = load_yaml(ROOT / "examples" / "inverse_cf4_o2_ar.yaml")
    if constraint_kind == "prior":
        inv_cfg["priors"] = [
            {
                "type": "log_gaussian",
                "path": "plasma_state.metastables.Ar_1s5[0]",
                "mean_log10": 14.7,
                "sigma_log10": 0.5,
            }
        ]
    else:
        inv_cfg["fit"]["regularization"]["smooth_arrays"] = [
            {
                "path": "plasma_state.radicals.O",
                "order": 2,
                "weight": 0.05,
            }
        ]

    with pytest.raises(ConfigSemanticError, match="does not contain a fitted parameter"):
        InverseSolver(case_cfg, inv_cfg)
