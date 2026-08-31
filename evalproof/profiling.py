"""Measurement production, without rule execution or quality judgments."""

from evalproof.measurement import Measurement
from evalproof.project_index import ProjectIndex


def collect_measurements(index: ProjectIndex) -> list[Measurement]:
    """v1.25 establishes the contract; v1.26 supplies dataset calculations."""
    return []
