"""Internal measurement values, independent of findings and severity policy."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any


@dataclass(frozen=True)
class Measurement:
    measurement_id: str
    artifact_id: str
    artifact_path: str
    scope: dict
    value: Any
    unit: str
    population_count: int
    coverage: dict
    parameters: dict
    method: str
    evidence: dict

    def __post_init__(self):
        if not isinstance(self.measurement_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", self.measurement_id):
            raise ValueError("Measurement ID must be a dotted lowercase identifier.")
        path = self.artifact_path
        if not isinstance(path, str) or not path or "\\" in path or PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive or ".." in PurePosixPath(path).parts:
            raise ValueError("Measurement artifact path must be root-relative POSIX.")
        if not isinstance(self.artifact_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.artifact_id):
            raise ValueError("Measurement requires a SHA-256 artifact ID.")
        if isinstance(self.population_count, bool) or not isinstance(self.population_count, int) or self.population_count < 0:
            raise ValueError("Measurement population_count must be a nonnegative integer.")
        if not isinstance(self.scope, dict) or not (
            self.scope == {"type": "artifact"} or (
                set(self.scope) == {"type", "field"} and self.scope["type"] == "field"
                and isinstance(self.scope["field"], str) and bool(self.scope["field"])
            )
        ):
            raise ValueError("Measurement scope must be artifact or a named field.")
        if not isinstance(self.coverage, dict) or set(self.coverage) != {"status", "reasons"} or self.coverage["status"] not in {"complete", "partial", "unavailable"}:
            raise ValueError("Measurement requires explicit coverage status and reasons.")
        reasons = self.coverage["reasons"]
        if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons) or reasons != sorted(set(reasons)):
            raise ValueError("Measurement coverage reasons must be sorted unique strings.")
        if not isinstance(self.parameters, dict) or not isinstance(self.evidence, dict):
            raise ValueError("Measurement parameters and evidence must be objects.")
        if not isinstance(self.unit, str) or not self.unit or not isinstance(self.method, str) or not re.fullmatch(r"[a-z][a-z0-9_]*/v[1-9][0-9]*", self.method):
            raise ValueError("Measurement needs a unit and a versioned method identifier.")
        self._canonical_payload()

    def _canonical_payload(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    @property
    def fingerprint(self):
        return "sha256:" + hashlib.sha256(self._canonical_payload().encode("utf-8")).hexdigest()

    def to_dict(self):
        payload = asdict(self)
        payload["fingerprint"] = self.fingerprint
        return payload
