
from __future__ import annotations

from typing import Any, Dict


def instrument_capabilities(inst_cfg: Dict[str, Any]) -> Dict[str, bool]:
    bin_nm = float(inst_cfg.get("bin_nm", 1.0))
    lsf = inst_cfg.get("lsf", {})
    fwhm = float(lsf.get("fwhm_nm", lsf.get("fwhm_g_nm", bin_nm)))
    low_res = (bin_nm >= 0.2) or (fwhm >= 0.2)
    high_res = (bin_nm <= 0.05) and (fwhm <= 0.1)
    return {"low_res": low_res, "high_res": high_res}


def all_instruments_low_res(inst_cfgs: list[Dict[str, Any]]) -> bool:
    return all(instrument_capabilities(c)["low_res"] for c in inst_cfgs)
