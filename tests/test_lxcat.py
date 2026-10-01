from __future__ import annotations

from pathlib import Path

import pytest

from oescr.data.lxcat import load_lxcat_cross_section, load_lxcat_dataset, select_lxcat_process


def _write_fixture(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "LXCat, www.lxcat.net",
                "Generated on 01 Jan 2026. All rights reserved.",
                "DATABASE: unit database",
                "ELASTIC",
                "Ar",
                " 1.36e-5",
                "PROCESS: E + Ar -> E + Ar, Elastic",
                "COLUMNS: Energy (eV) | Cross section (m2)",
                "-----------------------------",
                " 0.0 1.0e-20",
                " 1.0 2.0e-20",
                "-----------------------------",
                "ATTACHMENT",
                "O2 -> O- + O",
                "PROCESS: E + O2 -> O- + O, Attachment",
                "COLUMNS: Energy (eV) | Cross section (m2)",
                "-----------------------------",
                " 0.1 0.0",
                " 1.0 3.0e-21",
                "-----------------------------",
            ]
        ),
        encoding="utf-8",
    )


def test_lxcat_dataset_inventory_and_selection(tmp_path: Path) -> None:
    source = tmp_path / "Cross section.txt"
    _write_fixture(source)

    dataset = load_lxcat_dataset(source)

    assert dataset.database == "unit database"
    assert dataset.generated_on == "01 Jan 2026"
    assert [process.collision_type for process in dataset.processes] == ["ELASTIC", "ATTACHMENT"]
    attachment = select_lxcat_process(dataset, "E + O2 -> O- + O, Attachment")
    assert attachment.target_label == "O2 -> O- + O"
    assert attachment.parameter_line is None
    assert attachment.energy_eV.tolist() == [0.1, 1.0]

    curve = load_lxcat_cross_section(source, "Ar")
    assert curve.metadata["database"] == "unit database"
    assert curve.sigma_m2.tolist() == [1.0e-20, 2.0e-20]


def test_lxcat_selection_rejects_missing_process(tmp_path: Path) -> None:
    source = tmp_path / "Cross section.txt"
    _write_fixture(source)

    with pytest.raises(ValueError, match="found 0"):
        select_lxcat_process(load_lxcat_dataset(source), "missing")
