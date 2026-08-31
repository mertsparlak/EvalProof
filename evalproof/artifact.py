"""Artifact model, format detection, role detection heuristics, and content access."""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Union, Tuple
import yaml

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback if needed

from evalproof.config import Config, ArtifactOverride
from evalproof.finding import Diagnostic, DiagnosticSeverity, DiagnosticCode


# Format mapping
EXTENSION_FORMAT_MAP: Dict[str, str] = {
    ".parquet": "parquet",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".csv": "csv",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "plain_text",
    ".text": "plain_text",
}

SUPPORTED_ROLES: Set[str] = {
    "training_dataset",
    "evaluation_dataset",
    "benchmark_dataset",
    "evaluation_result",
    "prompt_template",
    "rag_document",
    "configuration",
    "unknown",
}


def compute_artifact_id(rel_posix_path: str) -> str:
    """Compute artifact ID: sha256:<sha256 of repository-relative POSIX path>."""
    p = rel_posix_path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    digest = hashlib.sha256(p.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def detect_file_format(posix_path: str) -> Optional[str]:
    """Detect file format based on extension."""
    ext = Path(posix_path).suffix.lower()
    return EXTENSION_FORMAT_MAP.get(ext)


def detect_heuristic_roles(posix_path: str, fmt: str) -> Set[str]:
    """Detect artifact roles based on documented path and filename heuristics."""
    p_lower = posix_path.lower()
    p_check = f"/{p_lower}"
    filename = Path(p_lower).name
    roles: Set[str] = set()

    # training_dataset
    if fmt in {"json", "jsonl", "csv", "yaml", "toml", "parquet"}:
        if any(seg in p_check for seg in ["/train/", "/training/", "/finetune/"]) or \
           any(kw in filename for kw in ["train", "training", "finetune"]):
            roles.add("training_dataset")

    # evaluation_dataset
    if fmt in {"json", "jsonl", "csv", "yaml", "toml", "parquet"}:
        if any(seg in p_check for seg in ["/eval/", "/evals/", "/evaluation/", "/test/", "/tests/", "/val/", "/valid/", "/validation/"]) or \
           any(kw in filename for kw in ["eval", "evaluation", "test", "golden", "expected", "val", "valid", "validation"]):
            roles.add("evaluation_dataset")

    # benchmark_dataset
    if fmt in {"json", "jsonl", "csv", "yaml", "toml", "parquet"}:
        if any(seg in p_check for seg in ["/benchmark/", "/benchmarks/", "/leaderboard/"]) or \
           any(kw in filename for kw in ["benchmark", "bench", "leaderboard"]):
            roles.add("benchmark_dataset")

    # evaluation_result
    if fmt in {"json", "jsonl", "csv", "yaml", "toml", "parquet"}:
        if any(seg in p_check for seg in ["/result/", "/results/", "/report/", "/reports/", "/run/", "/runs/"]) or \
           any(kw in filename for kw in ["result", "results", "scores", "metrics", "baseline", "run"]):
            roles.add("evaluation_result")

    # prompt_template
    if fmt in {"markdown", "plain_text", "json", "yaml", "toml"}:
        if any(seg in p_check for seg in ["/prompt/", "/prompts/", "/template/", "/templates/"]) or \
           any(kw in filename for kw in ["prompt", "template", "system", "instruction"]):
            roles.add("prompt_template")

    # rag_document
    if fmt in {"markdown", "plain_text", "json", "jsonl", "csv", "yaml", "toml", "parquet"}:
        if any(seg in p_check for seg in ["/rag/", "/retrieval/", "/corpus/", "/knowledge/", "/kb/", "/docs/", "/documents/"]) or \
           any(kw in filename for kw in ["corpus", "knowledge", "retrieval", "context", "source"]):
            roles.add("rag_document")

    # configuration
    if fmt in {"json", "yaml", "toml"}:
        if filename in {"evalproof.yaml", "evalproof.yml", "config.yaml", "config.yml", "config.json", "settings.yaml", "settings.yml", "settings.json"}:
            roles.add("configuration")

    if not roles:
        roles.add("unknown")

    return roles


@dataclass
class Artifact:
    id: str
    path: str  # repository-relative POSIX path
    format: str
    roles: Set[str] = field(default_factory=set)
    role_source: str = "heuristic"
    metadata: Dict[str, Any] = field(default_factory=dict)
    full_disk_path: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def read_text(self) -> str:
        """Read artifact full raw text."""
        if self.format == "parquet":
            return ""
        if not self.full_disk_path or not os.path.exists(self.full_disk_path):
            return ""
        with open(self.full_disk_path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()

    def read_bytes(self) -> bytes:
        if not self.full_disk_path or not os.path.exists(self.full_disk_path):
            return b""
        return Path(self.full_disk_path).read_bytes()

    def read_validated_dataset_text(self) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Audit original bytes before deriving any dataset row identities."""
        raw = self.read_bytes()
        invalid_range = None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            invalid_range = {"offset": error.start, "length": error.end - error.start}
            text = ""
        nul_count = raw.count(b"\x00")
        if invalid_range is None and nul_count == 0:
            return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n"), None
        offsets = []
        start = 0
        for _ in range(min(nul_count, 20)):
            offset = raw.find(b"\x00", start)
            offsets.append(offset)
            start = offset + 1
        return "", {
            "artifact_path": self.path,
            "byte_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw),
            "invalid_utf8_range": invalid_range,
            "nul_byte_count": nul_count,
            "sample_nul_offsets": offsets,
            "nul_offsets_truncated": nul_count > len(offsets),
        }


def create_artifact_from_file(
    scan_root: str,
    posix_path: str,
    config: Config,
) -> Optional[Artifact]:
    """Detect format and roles for a file, returning an Artifact or None if not candidate."""
    full_disk_path = str(Path(scan_root) / posix_path)

    # Check explicit config overrides for role
    config_override_roles: Optional[List[str]] = None
    for override in config.artifacts:
        if override.path == posix_path:
            config_override_roles = override.roles
            break

    fmt = detect_file_format(posix_path)

    # If unsupported extension
    if fmt is None:
        if config_override_roles is not None:
            # Treat configured file with unsupported extension as plain_text with diagnostic
            fmt = "plain_text"
            art = Artifact(
                id=compute_artifact_id(posix_path),
                path=posix_path,
                format=fmt,
                roles=set(config_override_roles),
                role_source="config",
                full_disk_path=full_disk_path,
            )
            art.diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.WARNING.value,
                    code=DiagnosticCode.ARTIFACT_UNSUPPORTED_EXTENSION.value,
                    message=f"Configured artifact path '{posix_path}' has unsupported extension; treating as plain text.",
                    path=posix_path,
                )
            )
            return art
        else:
            # Files with unsupported extensions are not candidates unless configured
            return None

    # Supported format detected
    if config_override_roles is not None:
        assigned_roles = set(config_override_roles)
        role_source = "config"
    else:
        assigned_roles = detect_heuristic_roles(posix_path, fmt)
        role_source = "heuristic"

    artifact = Artifact(
        id=compute_artifact_id(posix_path),
        path=posix_path,
        format=fmt,
        roles=assigned_roles,
        role_source=role_source,
        full_disk_path=full_disk_path,
    )

    incompatible_split_roles = (
        "training_dataset" in assigned_roles
        and bool(assigned_roles.intersection({"evaluation_dataset", "benchmark_dataset"}))
    )
    if role_source == "heuristic" and incompatible_split_roles:
        artifact.diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity.WARNING.value,
                code=DiagnosticCode.ARTIFACT_ROLE_CONFLICT.value,
                message=(
                    f"Artifact '{posix_path}' was heuristically assigned incompatible split roles: "
                    f"{', '.join(sorted(assigned_roles.intersection({'training_dataset', 'evaluation_dataset', 'benchmark_dataset'})))}."
                ),
                path=posix_path,
                details={"roles": sorted(assigned_roles)},
            )
        )

    return artifact
