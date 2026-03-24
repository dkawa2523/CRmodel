
#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import csv
from pathlib import Path

from oescr.forward.model import OESCRModel


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
            with out_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["wavelength_nm", "intensity"])
                for wl, it in zip(spec["wavelength_nm"], spec["intensity"]):
                    writer.writerow([f"{wl:.8f}", f"{it:.12e}"])

    print(f"Forward spectra written to: {out_dir}")


if __name__ == "__main__":
    main()
