#!/usr/bin/env python
"""Prepare or execute an independent BOLSIG+ pure-gas reference run.

This producer deliberately imports no OESCR modules.  It writes the official
``bolsigminus`` instruction format and records immutable input identities.  A
separate OESCR command imports the frozen EEDF and rate tables afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

REFERENCE_FORMAT = "oescr_bolsig_reference_run/v1"
DEFAULT_FIELDS_TD = (10.0, 30.0, 50.0, 100.0, 200.0, 300.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_fields(values: Sequence[float]) -> tuple[float, ...]:
    fields = tuple(float(value) for value in values)
    if not fields or any(value <= 0.0 for value in fields):
        raise ValueError("Reduced fields must be positive.")
    if len(set(fields)) != len(fields):
        raise ValueError("Reduced fields must be unique.")
    return fields


def render_bolsig_instructions(
    collision_file: Path,
    result_filename: str,
    reduced_fields_Td: Sequence[float],
    *,
    species: str,
) -> str:
    """Render the BOLSIG+ 07/2024 console instruction file."""

    fields = _validated_fields(reduced_fields_Td)
    run_values = "\n".join(f"{value:g}" for value in fields)
    return f"""! OESCR external-reference producer; imports no OESCR physics
READCOLLISIONS
{collision_file.resolve()} / File
{species} / Species
1 / Extrapolate: 0=No; 1=Yes
CONDITIONS
VAR / Electric field / N (Td)
0. / Angular field frequency / N (m3/s)
0. / Cosine of E-B field angle
300. / Gas temperature (K)
0. / Excitation temperature (K); zero disables automatic superelastic collisions
0. / Transition energy (eV)
0. / Ionization degree
3e22 / Gas particle density (1/m3)
1. / Ion charge parameter
1. / Ion/neutral mass ratio
1 / e-e momentum effects
1 / Energy sharing: equal
1 / Growth: temporal
0. / Maxwellian mean energy (eV); zero solves the Boltzmann equation
400 / Number of grid points
0 / Manual grid: automatic
200. / Manual maximum energy (eV)
1e-10 / Precision
1e-4 / Convergence
1000 / Maximum number of iterations
1.0 / Gas composition fraction
1 / Normalize composition to unity
RUN
{run_values}
SAVERESULTS
{result_filename} / File
1 / Format: run by run
1 / Conditions
1 / Transport coefficients
1 / Rate coefficients
0 / Reverse rate coefficients
0 / Energy loss coefficients
1 / Distribution function
0 / Skip failed runs
END
"""


def _base_manifest(
    collision_file: Path,
    instruction_file: Path,
    result_file: Path,
    reduced_fields_Td: Sequence[float],
    species: str,
) -> dict[str, object]:
    return {
        "format": REFERENCE_FORMAT,
        "reference_solver": {"name": "BOLSIG+ bolsigminus", "target_version": "07/2024"},
        "producer": {"script": Path(__file__).name, "imports_oescr": False},
        "collision_input": {
            "path": str(collision_file.resolve()),
            "sha256": _sha256(collision_file),
            "species": species,
        },
        "instruction": {
            "path": instruction_file.name,
            "sha256": _sha256(instruction_file),
        },
        "result": {"path": result_file.name, "status": "not_executed"},
        "conditions": {
            "reduced_field_Td": list(_validated_fields(reduced_fields_Td)),
            "gas_temperature_K": 300.0,
            "gas_mixture": {species: 1.0},
            "growth_model": "temporal",
        },
    }


def _execute(executable: Path, instruction_file: Path, result_file: Path) -> dict[str, object]:
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"BOLSIG+ executable is missing: {executable}")
    completed = subprocess.run(
        [str(executable), instruction_file.name],
        cwd=instruction_file.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    (instruction_file.parent / "execution_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (instruction_file.parent / "execution_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"bolsigminus failed with exit code {completed.returncode}.")
    if not result_file.is_file():
        raise RuntimeError(f"bolsigminus did not create the declared result: {result_file}")
    record: dict[str, object] = {
        "path": result_file.name,
        "status": "completed",
        "sha256": _sha256(result_file),
        "executable_sha256": _sha256(executable),
        "command": [str(executable), instruction_file.name],
    }
    log_file = instruction_file.parent / "bolsiglog.txt"
    if log_file.is_file():
        record["log_sha256"] = _sha256(log_file)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collision_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--species", default="Ar")
    parser.add_argument("--field", type=float, action="append", dest="fields")
    parser.add_argument("--expected-collision-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()

    collision_file = args.collision_file.resolve()
    if not collision_file.is_file():
        parser.error(f"collision file is missing: {collision_file}")
    collision_hash = _sha256(collision_file)
    if args.expected_collision_sha256 and collision_hash != args.expected_collision_sha256.lower():
        parser.error(
            "collision SHA-256 mismatch: "
            f"expected {args.expected_collision_sha256.lower()}, got {collision_hash}"
        )
    if args.execute and args.executable is None:
        parser.error("--executable is required with --execute")

    fields = _validated_fields(args.fields or DEFAULT_FIELDS_TD)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    instruction_file = output_dir / "pure_gas_reference.in"
    result_file = output_dir / "bolsig_results.dat"
    instruction_file.write_text(
        render_bolsig_instructions(
            collision_file,
            result_file.name,
            fields,
            species=args.species,
        ),
        encoding="utf-8",
    )
    manifest = _base_manifest(
        collision_file,
        instruction_file,
        result_file,
        fields,
        args.species,
    )
    result_status = "not_executed"
    if args.execute:
        result_record = _execute(args.executable, instruction_file, result_file)
        manifest["result"] = result_record
        result_status = str(result_record["status"])
    manifest_file = output_dir / "run_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"instructions: {instruction_file}")
    print(f"manifest:     {manifest_file}")
    print(f"status:       {result_status}")


if __name__ == "__main__":
    main()
