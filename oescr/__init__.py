"""OESCR: research scaffold for low-pressure semiconductor plasma OES.

Top-level workflow classes are loaded lazily so importing a low-level OESCR
submodule does not also import optimization and reporting dependencies.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

__all__ = ["OESCRModel", "InverseSolver"]
try:
    __version__ = version("oescr")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0+unknown"


def __getattr__(name: str) -> Any:
    if name == "OESCRModel":
        from .forward.model import OESCRModel

        return OESCRModel
    if name == "InverseSolver":
        from .inverse.optimize import InverseSolver

        return InverseSolver
    raise AttributeError(f"module 'oescr' has no attribute {name!r}")
