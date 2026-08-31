"""Finding and Diagnostic models, canonical serialization, and fingerprinting."""

from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_RANK: Dict[str, int] = {
    Severity.CRITICAL.value: 4,
    Severity.HIGH.value: 3,
    Severity.MEDIUM.value: 2,
    Severity.LOW.value: 1,
}


class Confidence(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    HEURISTIC = "heuristic"


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCode(str, Enum):
    ARTIFACT_OPTIONAL_DEPENDENCY_MISSING = "artifact.optional_dependency_missing"
    ARTIFACT_UNSUPPORTED_PARQUET_SCHEMA = "artifact.unsupported_parquet_schema"
    ARTIFACT_PROVENANCE_SOURCE_UNREADABLE = "artifact.provenance_source_unreadable"
    ARTIFACT_INVALID_TEXT_ENCODING = "artifact.invalid_text_encoding"
    ARTIFACT_PARSE_FAILED = "artifact.parse_failed"
    ARTIFACT_ROW_PARSE_FAILED = "artifact.row_parse_failed"
    ARTIFACT_ROW_LIMIT_REACHED = "artifact.row_limit_reached"
    ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED = "artifact.file_size_limit_exceeded"
    ARTIFACT_UNSUPPORTED_EXTENSION = "artifact.unsupported_extension"
    CONFIG_INVALID = "config.invalid"
    RULE_RECOVERABLE_ERROR = "rule.recoverable_error"
    ARTIFACT_ROLE_CONFLICT = "artifact.role_conflict"


def canonical_json_dumps(obj: Any) -> str:
    """Canonical JSON serialization for deterministic hashing.

    - Keys sorted lexicographically
    - No insignificant whitespace (separators=(',', ':'))
    - Compact round-trippable numbers
    - UTF-8 text semantics
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class Location:
    role: Optional[str] = None
    path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    row: Optional[int] = None
    json_pointer: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for key in ["role", "path", "line", "column", "row", "json_pointer", "field"]:
            val = getattr(self, key)
            if val is not None:
                result[key] = val
        return result

    def to_stable_dict(self) -> Dict[str, Any]:
        return self.to_dict()


@dataclass
class Finding:
    rule_id: str
    severity: str
    confidence: str
    title: str
    message: str
    impact: str
    recommendation: str
    evidence: Dict[str, Any]
    locations: List[Location] = field(default_factory=list)
    fingerprint: Optional[str] = None

    def __post_init__(self):
        if self.fingerprint is None:
            self.fingerprint = self.compute_fingerprint()

    def compute_fingerprint(self) -> str:
        stable_locations = [loc.to_stable_dict() for loc in self.locations]
        payload = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "locations": stable_locations,
            "evidence": self.evidence,
        }
        canonical_str = canonical_json_dumps(payload)
        digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "title": self.title,
            "message": self.message,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "locations": [loc.to_dict() for loc in self.locations],
            "evidence": self.evidence,
            "fingerprint": self.fingerprint,
        }


@dataclass
class Diagnostic:
    severity: str
    code: str
    message: str
    path: Optional[str] = None
    line: Optional[int] = None
    row: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            res["path"] = self.path
        if self.line is not None:
            res["line"] = self.line
        if self.row is not None:
            res["row"] = self.row
        if self.details is not None:
            res["details"] = self.details
        return res
