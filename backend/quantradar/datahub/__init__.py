"""Versioned supplemental research data for QuantRadar.

The base investment_data Dolt repository is never mutated here.  A release is a
pair of immutable Dolt commits published through a small manifest.
"""

from .release import ReleaseStore

__all__ = ["ReleaseStore"]
