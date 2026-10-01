from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_prepare_bolsig_reference_run_writes_independent_six_condition_contract(
    tmp_path: Path,
) -> None:
    collision_file = tmp_path / "Ar_collision.txt"
    collision_file.write_text("minimal test collision identity\n", encoding="utf-8")
    expected_hash = hashlib.sha256(collision_file.read_bytes()).hexdigest()
    output_dir = tmp_path / "reference"

    subprocess.run(
        [
            sys.executable,
            "scripts/prepare_bolsig_reference_run.py",
            str(collision_file),
            "--output-dir",
            str(output_dir),
            "--expected-collision-sha256",
            expected_hash,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    instructions = (output_dir / "pure_gas_reference.in").read_text(encoding="utf-8")
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert "CONDITIONS\nVAR / Electric field / N (Td)" in instructions
    assert "RUN\n10\n30\n50\n100\n200\n300\nSAVERESULTS" in instructions
    assert "1 / Format: run by run" in instructions
    assert "1 / Distribution function" in instructions
    assert manifest["producer"]["imports_oescr"] is False
    assert manifest["collision_input"]["sha256"] == expected_hash
    assert manifest["conditions"]["reduced_field_Td"] == [10.0, 30.0, 50.0, 100.0, 200.0, 300.0]
    assert manifest["result"]["status"] == "not_executed"


def test_prepare_bolsig_reference_producer_does_not_import_oescr() -> None:
    source = Path("scripts/prepare_bolsig_reference_run.py").read_text(encoding="utf-8")

    assert "from oescr" not in source
    assert "import oescr" not in source
