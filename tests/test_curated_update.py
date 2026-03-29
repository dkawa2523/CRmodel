import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.forward.model import OESCRModel
from oescr.inverse.objectives import (
    Measurement,
    fit_gain_offsets_for_instrument,
    gain_prior_residual,
    gain_tilt_prior_residual,
    window_ratio_pair_residuals,
    window_features,
    window_fit_residuals,
    window_ratio_residuals,
)
from oescr.inverse.priors import prior_residuals


def test_curated_nf3_forward_runs():
    case = Path('examples/case_skeleton_nf3_ar.yaml')
    model = OESCRModel.from_yaml(case)
    result = model.predict()
    assert 'uvvis_lowres' in result.spectra
    assert len(result.zone_populations) == 3


def test_curated_cl2_forward_runs():
    case = Path('examples/case_skeleton_cl2_ar.yaml')
    model = OESCRModel.from_yaml(case)
    result = model.predict()
    assert 'uvvis_lowres' in result.spectra
    assert len(result.zone_populations) == 3


def test_window_fit_zero_for_identical_signals():
    wl = np.linspace(700.0, 710.0, 41)
    y = np.exp(-0.5 * ((wl - 703.7) / 0.3) ** 2) + 0.1 + 0.01 * (wl - wl.mean())
    r = window_fit_residuals(
        wl,
        y,
        y,
        center_nm=703.7,
        half_width_nm=1.0,
        baseline_mode='local_linear',
        normalization='area',
        local_gain=False,
    )
    assert np.allclose(r, 0.0, atol=1.0e-10)


def test_window_features_baseline_corrected_area_positive():
    wl = np.linspace(700.0, 710.0, 41)
    y = 0.2 + 0.02 * (wl - wl.mean()) + 2.0 * np.exp(-0.5 * ((wl - 703.7) / 0.3) ** 2)
    feats = window_features(wl, y, center_nm=703.7, half_width_nm=1.0, baseline_mode='local_linear')
    assert feats['area'] > 0.0
    assert feats['peak'] > 0.0


def test_window_ratio_zero_for_identical_feature_ratios():
    windows = [
        {"name": "ref", "use_peak": True, "use_area": True},
        {"name": "line_a", "use_peak": True, "use_area": True},
        {"name": "line_b", "use_peak": True, "use_area": True},
    ]
    pred = {
        "ref": {"area": 4.0, "peak": 2.0},
        "line_a": {"area": 2.0, "peak": 1.0},
        "line_b": {"area": 1.0, "peak": 0.5},
    }
    meas = {
        "ref": {"area": 8.0, "peak": 4.0},
        "line_a": {"area": 4.0, "peak": 2.0},
        "line_b": {"area": 2.0, "peak": 1.0},
    }
    r = window_ratio_residuals(
        windows,
        pred,
        meas,
        metric="peak",
        reference_window="ref",
        min_relative_signal=0.0,
    )
    assert np.allclose(r, 0.0, atol=1.0e-12)


def test_gain_prior_zero_at_target_gain():
    r = gain_prior_residual(
        gain=1.0,
        inst_cfg={"nuisance": {"gain": 1.0}},
        weight=0.2,
        target=None,
        sigma_log10=0.2,
    )
    assert np.allclose(r, 0.0, atol=1.0e-12)


def test_gain_tilt_prior_zero_at_zero_tilt_and_positive_otherwise():
    zero = gain_tilt_prior_residual(tilt=0.0, weight=0.5, sigma=0.25)
    nonzero = gain_tilt_prior_residual(tilt=0.2, weight=0.5, sigma=0.25)
    assert np.allclose(zero, 0.0, atol=1.0e-12)
    assert nonzero.shape == (1,)
    assert abs(float(nonzero[0])) > 0.0


def test_instrument_scope_gain_fits_single_shared_gain():
    wl = np.linspace(700.0, 704.0, 9)
    pred = {"wavelength_nm": wl, "intensity": np.linspace(1.0, 2.0, len(wl))}
    meas0 = Measurement(wl, 2.0 * pred["intensity"])
    meas1 = Measurement(wl, 2.0 * pred["intensity"])
    gains = fit_gain_offsets_for_instrument(
        "uvvis",
        [meas0, meas1],
        {"chord_0": pred, "chord_1": pred},
        {"nuisance": {"gain": 1.0}, "baseline": {"offset": 0.0}},
        auto_gain=True,
        auto_offset=False,
        gain_scope="instrument",
    )
    assert np.isclose(gains["chord_0"]["gain"], 2.0)
    assert np.isclose(gains["chord_1"]["gain"], 2.0)
    assert np.isclose(gains["chord_0"]["tilt"], 0.0)
    assert np.isclose(gains["chord_1"]["tilt"], 0.0)


def test_instrument_scope_gain_tilt_fits_linear_spectral_slope():
    wl = np.linspace(400.0, 900.0, 251)
    pred_intensity = 1.0 + 0.3 * np.sin(np.linspace(0.0, 3.0 * np.pi, len(wl)))
    pred = {"wavelength_nm": wl, "intensity": pred_intensity}
    wl_norm = (wl - 0.5 * (wl.min() + wl.max())) / (0.5 * (wl.max() - wl.min()))
    gain_true = 1.8
    tilt_true = 0.22
    offset_true = 0.0
    meas_y = gain_true * (1.0 + tilt_true * wl_norm) * pred_intensity + offset_true
    meas = Measurement(wl, meas_y)
    gains = fit_gain_offsets_for_instrument(
        "uvvis",
        [meas],
        {"chord_0": pred},
        {"nuisance": {"gain": 1.0}, "baseline": {"offset": 0.0}},
        auto_gain=True,
        auto_offset=False,
        auto_gain_tilt=True,
        gain_scope="instrument",
    )
    got = gains["chord_0"]
    assert np.isclose(got["gain"], gain_true, rtol=1.0e-3, atol=1.0e-3)
    assert np.isclose(got["tilt"], tilt_true, rtol=1.0e-3, atol=1.0e-3)
    assert np.isclose(got["offset"], offset_true, rtol=1.0e-3, atol=1.0e-3)


def test_window_ratio_pair_zero_for_identical_pair_ratio():
    pred = {
        "line_a": {"area": 4.0, "peak": 2.0},
        "line_b": {"area": 2.0, "peak": 1.0},
    }
    meas = {
        "line_a": {"area": 8.0, "peak": 4.0},
        "line_b": {"area": 4.0, "peak": 2.0},
    }
    residuals = window_ratio_pair_residuals(
        pred,
        meas,
        [{"name": "a_over_b", "numerator": "line_a", "denominator": "line_b", "metric": "peak"}],
        default_metric="peak",
        default_min_relative_signal=0.0,
    )
    assert np.allclose(residuals[0], 0.0, atol=1.0e-12)


def test_log_gaussian_array_prior_zero_when_values_match():
    case_cfg = {"plasma_state": {"ne_shells_m3": [1.0e16, 8.0e15, 6.0e15]}}
    inv_cfg = {
        "priors": [
            {
                "type": "log_gaussian",
                "path": "plasma_state.ne_shells_m3",
                "mean_log10": [16.0, np.log10(8.0e15), np.log10(6.0e15)],
                "sigma_log10": 0.2,
            }
        ]
    }
    r = prior_residuals(case_cfg, inv_cfg)
    assert np.allclose(r, 0.0, atol=1.0e-12)
