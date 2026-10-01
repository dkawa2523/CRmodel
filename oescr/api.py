"""Public convenience API for decoupled use of OESCR submodels.

Beyond the numerical kernels, this module now also exposes the schema validators
and plugin registries that define the stable extension surface of the code base.
"""

from .data.atomic_db import StateRegistry
from .data.cross_section_db import CrossSectionLibrary
from .data.lxcat import (
    LXCatDataset,
    LXCatProcess,
    load_lxcat_cross_section,
    load_lxcat_dataset,
    select_lxcat_process,
)
from .forward.compiled import CompiledCase, compile_case
from .forward.model import OESCRModel
from .geometry import GEOMETRY_PLUGINS, build_W_axisym_shell, get_geometry_plugin, shell_centers, shell_edges
from .instrument.baseline import BASELINE_PLUGINS
from .instrument.lsf import LSF_PLUGINS
from .instrument.spec import InstrumentSpec, normalize_instrument_config
from .instrument.throughput import THROUGHPUT_PLUGINS
from .io.schema import AVAILABLE_SCHEMAS, validate_document
from .io.species_packs import compose_species_packs
from .physics.bands import BAND_EMISSION_PLUGINS, BAND_PROFILE_PLUGINS
from .physics.cr_atomic import AtomicCRSolver
from .physics.cr_processes import (
    REACTION_FAMILIES,
    CompiledReactionProcess,
    compile_reaction_processes,
)
from .physics.eedf import (
    EEDF_PLUGINS,
    EEDFPlugin,
    bi_maxwell_energy_pdf,
    build_eedf_for_zone,
    build_energy_grid,
    druyvesteyn_energy_pdf,
    eedf_model_kind,
    maxwell_energy_pdf,
    resolve_eedf_plugin_spec,
    tabulated_energy_pdf,
)
from .physics.quality import DiagnosticPolicyError, DiagnosticReport
from .physics.rates import REACTION_RATE_PLUGINS, RateCalculator, resolve_reaction_rate_spec
from .physics.trapping import TRAPPING_PLUGINS
from .physics.wall import WALL_LOSS_PLUGINS

__all__ = [
    "AVAILABLE_SCHEMAS",
    "AtomicCRSolver",
    "BASELINE_PLUGINS",
    "BAND_EMISSION_PLUGINS",
    "BAND_PROFILE_PLUGINS",
    "CrossSectionLibrary",
    "DiagnosticPolicyError",
    "DiagnosticReport",
    "CompiledCase",
    "CompiledReactionProcess",
    "EEDF_PLUGINS",
    "EEDFPlugin",
    "GEOMETRY_PLUGINS",
    "InstrumentSpec",
    "LSF_PLUGINS",
    "LXCatDataset",
    "LXCatProcess",
    "OESCRModel",
    "REACTION_RATE_PLUGINS",
    "REACTION_FAMILIES",
    "RateCalculator",
    "StateRegistry",
    "THROUGHPUT_PLUGINS",
    "TRAPPING_PLUGINS",
    "WALL_LOSS_PLUGINS",
    "bi_maxwell_energy_pdf",
    "build_W_axisym_shell",
    "build_energy_grid",
    "build_eedf_for_zone",
    "compile_case",
    "compile_reaction_processes",
    "compose_species_packs",
    "druyvesteyn_energy_pdf",
    "eedf_model_kind",
    "get_geometry_plugin",
    "load_lxcat_cross_section",
    "load_lxcat_dataset",
    "maxwell_energy_pdf",
    "normalize_instrument_config",
    "resolve_eedf_plugin_spec",
    "resolve_reaction_rate_spec",
    "shell_centers",
    "shell_edges",
    "select_lxcat_process",
    "tabulated_energy_pdf",
    "validate_document",
]
