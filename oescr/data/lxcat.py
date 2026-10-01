"""Read native LXCat collision files without coupling them to a solver.

LXCat files remain external, licensed inputs.  This module only identifies
their process blocks, validates numeric tables, and exposes selected curves in
the same in-memory form used by the OESCR rate calculator.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .cross_section_db import CrossSection
from .provenance import file_sha256

COLLISION_TYPES = {"ELASTIC", "EFFECTIVE", "EXCITATION", "IONIZATION", "ATTACHMENT"}


@dataclass(frozen=True)
class LXCatProcess:
    index: int
    collision_type: str
    target_label: str
    parameter_line: str | None
    process_description: str
    metadata: dict[str, str]
    energy_eV: np.ndarray
    sigma_m2: np.ndarray
    curve_data_sha256: str


@dataclass(frozen=True)
class LXCatDataset:
    path: Path
    source_sha256: str
    database: str
    generated_on: str
    processes: tuple[LXCatProcess, ...]


def curve_data_sha256(energy_eV: np.ndarray, sigma_m2: np.ndarray) -> str:
    """Hash numeric curve content independently of its LXCat text envelope."""

    values = np.column_stack((energy_eV, sigma_m2)).astype("<f8", copy=False)
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def _metadata(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper().rstrip(".")
        value = value.strip()
        if key == "COMMENT" and key in result:
            result[key] = f"{result[key]} {value}".strip()
        elif value:
            result[key] = value
    return result


def _numeric_table(lines: list[str], label: str) -> tuple[np.ndarray, np.ndarray]:
    rows: list[tuple[float, float]] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            rows.append((float(fields[0]), float(fields[1])))
        except ValueError:
            continue
    if len(rows) < 2:
        raise ValueError(f"LXCat process '{label}' has fewer than two data rows.")
    values = np.asarray(rows, dtype=float)
    energy, sigma = values[:, 0], values[:, 1]
    if not np.all(np.isfinite(values)):
        raise ValueError(f"LXCat process '{label}' contains non-finite values.")
    if np.any(energy < 0.0) or np.any(np.diff(energy) <= 0.0):
        raise ValueError(f"LXCat process '{label}' has invalid energy values.")
    if np.any(sigma < 0.0):
        raise ValueError(f"LXCat process '{label}' has negative cross sections.")
    return energy, sigma


def _process_block(lines: list[str], start: int, end: int, index: int) -> LXCatProcess:
    collision_type = lines[start].strip()
    target_label = lines[start + 1].strip()
    parameter_line = None if collision_type == "ATTACHMENT" else lines[start + 2].strip()
    table_markers = [
        line_index
        for line_index in range(start + 2, end)
        if lines[line_index].strip().startswith("-----")
    ]
    if len(table_markers) < 2:
        raise ValueError(f"LXCat process '{target_label}' has no bounded numeric table.")
    table_start, table_end = table_markers[0], table_markers[1]
    metadata = _metadata(lines[start + 2 : table_start])
    energy, sigma = _numeric_table(lines[table_start + 1 : table_end], target_label)
    return LXCatProcess(
        index=index,
        collision_type=collision_type,
        target_label=target_label,
        parameter_line=parameter_line,
        process_description=metadata.get("PROCESS", target_label),
        metadata=metadata,
        energy_eV=energy,
        sigma_m2=sigma,
        curve_data_sha256=curve_data_sha256(energy, sigma),
    )


def load_lxcat_dataset(path: str | Path) -> LXCatDataset:
    """Parse all collision blocks and file-level provenance from an LXCat download."""

    source = Path(path).resolve()
    lines = source.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() in COLLISION_TYPES]
    if not starts:
        raise ValueError(f"LXCat file contains no collision blocks: {source}")
    ends = [*starts[1:], len(lines)]
    processes = tuple(
        _process_block(lines, start, end, index)
        for index, (start, end) in enumerate(zip(starts, ends, strict=True), start=1)
    )
    header = _metadata(lines[: starts[0]])
    generated_line = next((line.strip() for line in lines if line.startswith("Generated on ")), "")
    generated_on = generated_line.removeprefix("Generated on ").removesuffix(". All rights reserved.")
    return LXCatDataset(
        path=source,
        source_sha256=file_sha256(source),
        database=header.get("DATABASE", "unknown"),
        generated_on=generated_on,
        processes=processes,
    )


def select_lxcat_process(dataset: LXCatDataset, label: str) -> LXCatProcess:
    """Select exactly one process by its target label or full PROCESS description."""

    matches = [
        process
        for process in dataset.processes
        if label in {process.target_label, process.process_description}
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one LXCat process matching '{label}', found {len(matches)}.")
    return matches[0]


def load_lxcat_cross_section(path: str | Path, process_label: str) -> CrossSection:
    """Load one native LXCat process as an OESCR cross-section curve."""

    dataset = load_lxcat_dataset(path)
    process = select_lxcat_process(dataset, process_label)
    return CrossSection(
        energy_eV=process.energy_eV,
        sigma_m2=process.sigma_m2,
        path=f"{dataset.path}#{process.target_label}",
        sha256=process.curve_data_sha256,
        metadata={
            **process.metadata,
            "database": dataset.database,
            "source_sha256": dataset.source_sha256,
            "curve_data_sha256": process.curve_data_sha256,
            "process_label": process.target_label,
        },
    )
