
#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

from oescr.forward.model import OESCRModel
from oescr.forward.reporting import write_forward_diagnostics
from oescr.io.spectrum_csv import write_spectrum_csv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_yaml")
    ap.add_argument("--out", default="forward_output")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = OESCRModel.from_yaml(args.case_yaml)
    result = model.predict()

    for inst_id, chord_map in result.spectra.items():
        for chord_key, spec in chord_map.items():
            out_path = out_dir / f"{inst_id}_{chord_key}.csv"
            write_spectrum_csv(
                out_path,
                spec["wavelength_nm"],
                spec["intensity"],
                metadata={
                    "output_basis": spec["output_basis"],
                    "output_unit": spec["output_unit"],
                    "calibration_reference": spec["calibration_reference"],
                },
            )
    write_forward_diagnostics(result, out_dir / "diagnostics.yaml")

    print(f"Forward spectra written to: {out_dir}")


if __name__ == "__main__":
    main()
