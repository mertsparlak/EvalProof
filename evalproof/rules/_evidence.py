"""Private helpers for bounded, deterministic rule evidence."""

from typing import Any, List, Tuple


MAX_RELATED_EVIDENCE = 20


def cap_evidence_items(items: List[Any]) -> Tuple[List[Any], bool]:
    """Return a deterministic prefix and whether evidence was omitted."""
    return items[:MAX_RELATED_EVIDENCE], len(items) > MAX_RELATED_EVIDENCE
