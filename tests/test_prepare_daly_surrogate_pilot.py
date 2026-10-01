from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


def test_daly_surrogate_pilot_prepares_five_gas_setpoint_contract(tmp_path: Path) -> None:
    output_dir = tmp_path / "daly_pilot"
    subprocess.run(
        [
            sys.executable,
            "scripts/prepare_daly_surrogate_pilot.py",
            "--output-dir",
            str(output_dir),
            "--source-revision",
            "test-revision",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with (output_dir / "conditions.csv").open(encoding="utf-8", newline="") as stream:
        conditions = list(csv.DictReader(stream))
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    wavelengths = (output_dir / "wavelengths.csv").read_text(encoding="utf-8").splitlines()

    assert len(conditions) == 150
    assert Counter(row["gas_system"] for row in conditions) == {
        "Ar": 30,
        "O2": 30,
        "Ar_O2": 30,
        "CF4_O2": 30,
        "SF6_O2": 30,
    }
    assert len(wavelengths) == 3073
    assert manifest["producer"]["imports_oescr"] is False
    assert manifest["result"]["status"] == "not_executed"
    assert manifest["design"]["condition_count"] == 150
    assert manifest["evidence_boundary"]["does_not_support"] == [
        "held-out measured-spectrum validation",
        "electron temperature accuracy",
        "electron density accuracy",
        "EEDF accuracy",
    ]


def test_daly_setpoint_design_covers_each_active_axis_range(tmp_path: Path) -> None:
    output_dir = tmp_path / "daly_pilot"
    subprocess.run(
        [
            sys.executable,
            "scripts/prepare_daly_surrogate_pilot.py",
            "--output-dir",
            str(output_dir),
            "--source-revision",
            "test-revision",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with (output_dir / "conditions.csv").open(encoding="utf-8", newline="") as stream:
        conditions = list(csv.DictReader(stream))

    ar = [row for row in conditions if row["gas_system"] == "Ar"]
    cf4_o2 = [row for row in conditions if row["gas_system"] == "CF4_O2"]
    assert {float(row["icp_power_W"]) for row in ar} >= {480.0, 3000.0}
    assert {float(row["ar_flow_sccm"]) for row in ar} >= {3.5, 70.0}
    assert all(float(row["o2_flow_sccm"]) == 0.0 for row in ar)
    assert {float(row["cf4_flow_sccm"]) for row in cf4_o2} >= {4.2, 84.0}
    assert {float(row["o2_flow_sccm"]) for row in cf4_o2} >= {2.5, 50.0}
    assert {float(row["pressure_mTorr"]) for row in cf4_o2} >= {4.0, 90.0}


def test_daly_surrogate_producer_does_not_import_oescr() -> None:
    source = Path("scripts/prepare_daly_surrogate_pilot.py").read_text(encoding="utf-8")

    assert "from oescr" not in source
    assert "import oescr" not in source
