from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Mapping

import numpy as np
from scipy.signal import fftconvolve
from scipy.special import wofz

from ..plugins import PluginBase, PluginRegistry


LSF_PLUGINS: PluginRegistry["LSFPlugin"] = PluginRegistry("lsf")


class LSFPlugin(PluginBase):
    @abstractmethod
    def kernel(self, spec: Mapping[str, Any], dx_nm: float) -> np.ndarray:
        raise NotImplementedError


def gaussian_kernel(dx_nm: float, fwhm_nm: float, half_width_sigma: float = 5.0) -> np.ndarray:
    sigma = max(fwhm_nm / 2.35482004503, 1.0e-12)
    half = int(max(3, np.ceil(half_width_sigma * sigma / max(dx_nm, 1.0e-12))))
    x = np.arange(-half, half + 1, dtype=float) * dx_nm
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / np.sum(k)


def voigt_kernel(dx_nm: float, fwhm_g_nm: float, fwhm_l_nm: float, half_width_sigma: float = 10.0) -> np.ndarray:
    sigma = max(fwhm_g_nm / 2.35482004503, 1.0e-12)
    gamma = max(fwhm_l_nm / 2.0, 1.0e-12)
    half = int(max(5, np.ceil(half_width_sigma * max(sigma, gamma) / max(dx_nm, 1.0e-12))))
    x = np.arange(-half, half + 1, dtype=float) * dx_nm
    z = (x + 1j * gamma) / (sigma * np.sqrt(2.0))
    k = np.real(wofz(z)) / (sigma * np.sqrt(2.0 * np.pi))
    k = np.maximum(k, 0.0)
    return k / np.sum(k)


class _GaussianLSF(LSFPlugin):
    kind = "gaussian"
    description = "Gaussian line-spread function."
    config_schema = {
        "type": "object",
        "required": ["kind", "fwhm_nm"],
        "properties": {
            "kind": {"const": "gaussian"},
            "fwhm_nm": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def kernel(self, spec: Mapping[str, Any], dx_nm: float) -> np.ndarray:
        return gaussian_kernel(dx_nm, float(spec["fwhm_nm"]))


class _VoigtLSF(LSFPlugin):
    kind = "voigt"
    description = "Voigt line-spread function with Gaussian and Lorentzian widths."
    config_schema = {
        "type": "object",
        "required": ["kind", "fwhm_g_nm", "fwhm_l_nm"],
        "properties": {
            "kind": {"const": "voigt"},
            "fwhm_g_nm": {"type": "number", "exclusiveMinimum": 0},
            "fwhm_l_nm": {"type": "number", "exclusiveMinimum": 0},
        },
        "additionalProperties": False,
    }

    def kernel(self, spec: Mapping[str, Any], dx_nm: float) -> np.ndarray:
        return voigt_kernel(dx_nm, float(spec["fwhm_g_nm"]), float(spec["fwhm_l_nm"]))


LSF_PLUGINS.register(_GaussianLSF())
LSF_PLUGINS.register(_VoigtLSF())


def normalize_lsf_config(inst_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    lsf = dict(inst_cfg.get("lsf", {"kind": "gaussian", "fwhm_nm": 0.5}))
    lsf.setdefault("kind", "gaussian")
    if lsf["kind"] == "gaussian":
        lsf.setdefault("fwhm_nm", 0.5)
    return lsf


def apply_lsf(inst_cfg: Dict[str, Any], wavelength_nm: np.ndarray, intensity: np.ndarray) -> np.ndarray:
    spec = normalize_lsf_config(inst_cfg)
    plugin = LSF_PLUGINS.get(str(spec["kind"]))
    plugin.validate_config(spec)
    dx = float(np.mean(np.diff(wavelength_nm)))
    kern = plugin.kernel(spec, dx)
    return fftconvolve(intensity, kern, mode="same")
