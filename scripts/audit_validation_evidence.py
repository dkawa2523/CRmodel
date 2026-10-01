#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oescr.analysis.validation_evidence import assess_validation_evidence
from oescr.io.yaml_loader import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def _default_protocols() -> list[Path]:
    return sorted((ROOT / "examples" / "benchmarks").glob("*/validation.yaml"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit reproducibility and external-validation eligibility of evidence packages."
    )
    parser.add_argument("protocols", nargs="*", type=Path)
    parser.add_argument(
        "--require-external-quantitative",
        action="store_true",
        help="Fail unless every package is eligible for an external quantitative claim.",
    )
    args = parser.parse_args()

    protocols = args.protocols or _default_protocols()
    if not protocols:
        parser.error("no validation evidence declarations were found")

    assessments = []
    for protocol in protocols:
        assessment = assess_validation_evidence(load_yaml(protocol))
        assessments.append(assessment)
        declared = "READY" if assessment.declared_evidence_ready else "NOT READY"
        external = "READY" if assessment.external_quantitative_ready else "NOT READY"
        print(f"{assessment.validation_id}: declared={declared}; external_quantitative={external}")
        for check in assessment.checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"  [{status}] {check.name}: {check.detail}")
        for blocker in assessment.external_quantitative_blockers:
            print(f"  [BLOCKER] {blocker}")

    declared_ok = all(item.declared_evidence_ready for item in assessments)
    external_ok = all(item.external_quantitative_ready for item in assessments)
    passed = declared_ok and (external_ok if args.require_external_quantitative else True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
