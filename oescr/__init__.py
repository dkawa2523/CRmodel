"""OESCR: research scaffold for low-pressure semiconductor plasma OES.

Top-level exports stay intentionally small. The more granular, decoupled API is
available from :mod:`oescr.api`.
"""

from .forward.model import OESCRModel
from .inverse.optimize import InverseSolver

__all__ = ["OESCRModel", "InverseSolver"]
__version__ = "0.5.0-schema-plugin"
