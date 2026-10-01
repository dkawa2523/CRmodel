from __future__ import annotations

import numpy as np
import pytest

from oescr.analysis.benchmark_metrics import (
    aggregate_window_rows,
    mean_abs_relative_error,
    safe_corr,
    trend_label,
)


def test_benchmark_metrics_are_usable_without_report_rendering() -> None:
    entries = [
        {
            "scenario": "opt",
            "window_name": "Ar_750",
            "kind": "atomic_line",
            "family": "Ar",
            "area_ratio": 0.9,
            "peak_ratio": 1.1,
            "peak_shift_nm": -0.2,
            "measurement_area": 4.0,
        },
        {
            "scenario": "opt",
            "window_name": "Ar_750",
            "kind": "atomic_line",
            "family": "Ar",
            "area_ratio": 1.1,
            "peak_ratio": 0.9,
            "peak_shift_nm": 0.4,
            "measurement_area": 6.0,
        },
    ]

    rows = aggregate_window_rows(entries, ("window_name",))

    assert rows[0]["window_name"] == "Ar_750"
    assert rows[0]["kind"] == "atomic_line"
    assert rows[0]["family"] == "Ar"
    assert rows[0]["mean_area_ratio"] == pytest.approx(1.0)
    assert rows[0]["mean_peak_ratio"] == pytest.approx(1.0)
    assert rows[0]["mean_abs_peak_shift_nm"] == pytest.approx(0.3)
    assert rows[0]["mean_abs_measurement_area"] == pytest.approx(5.0)
    assert safe_corr(np.array([1.0, 2.0]), np.array([2.0, 4.0])) == pytest.approx(1.0)
    assert mean_abs_relative_error(np.array([1.0, 3.0]), np.array([1.0, 2.0])) == 0.25
    assert trend_label([3.0, 2.0, 1.0]) == "monotonic decrease from core to edge"
