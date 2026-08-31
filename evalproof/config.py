"""Configuration loading, validation, and schema definitions."""

from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import re
from typing import Dict, List, Optional, Set, Any
import yaml

from evalproof.finding import Severity


ALLOWED_TOP_LEVEL_KEYS: Set[str] = {
    "include",
    "exclude",
    "artifacts",
    "rules",
    "ci",
    "limits",
    "similarity",
}

ALLOWED_ROLES: Set[str] = {
    "training_dataset",
    "evaluation_dataset",
    "benchmark_dataset",
    "evaluation_result",
    "prompt_template",
    "rag_document",
    "configuration",
    "unknown",
}

ALLOWED_SEVERITIES: Set[str] = {
    Severity.CRITICAL.value,
    Severity.HIGH.value,
    Severity.MEDIUM.value,
    Severity.LOW.value,
}

DEFAULT_INCLUDES: List[str] = ["**/*"]

DEFAULT_EXCLUDES: List[str] = [
    ".git/**",
    "node_modules/**",
    ".venv/**",
    "venv/**",
    "__pycache__/**",
    "dist/**",
    "build/**",
    ".next/**",
    ".cache/**",
    "target/**",
    "coverage/**",
    "evalproof_report.json",
]

DEFAULT_FAIL_ON: str = Severity.HIGH.value
DEFAULT_MAX_FILE_MB: int = 100
DEFAULT_MAX_ROWS_PER_ARTIFACT: int = 250000

DATASET_SCHEMA_ROLES: Set[str] = {
    "training_dataset",
    "evaluation_dataset",
    "benchmark_dataset",
}

SCHEMA_FORMAT_EXTENSIONS: Set[str] = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".yaml",
    ".yml",
    ".toml",
}

ALLOWED_SCHEMA_TYPES: Set[str] = {
    "string",
    "integer",
    "number",
    "boolean",
    "object",
    "array",
}


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass
class FieldContract:
    type: str
    nullable: bool = False


@dataclass
class ArtifactSchemaContract:
    required: List[str]
    fields: Dict[str, FieldContract]


@dataclass
class ArtifactProvenanceContract:
    required: List[str] = field(default_factory=list)
    version: Optional[str] = None
    fingerprint: Optional[str] = None
    source: Dict[str, Optional[str]] = field(default_factory=dict)
    generator: Dict[str, Optional[str]] = field(default_factory=dict)
    license: Optional[str] = None


@dataclass
class ArtifactOverride:
    path: str
    roles: List[str]
    schema: Optional[ArtifactSchemaContract] = None
    provenance: Optional[ArtifactProvenanceContract] = None


@dataclass
class LimitsConfig:
    max_file_mb: int = DEFAULT_MAX_FILE_MB
    max_rows_per_artifact: int = DEFAULT_MAX_ROWS_PER_ARTIFACT


@dataclass
class SimilarityConfig:
    enabled: bool = True
    shingle_size: int = 3
    num_hashes: int = 64
    bands: int = 16
    threshold: float = 0.85
    focus_roles: List[str] = field(default_factory=lambda: ["user"])
    focus_fields: List[str] = field(default_factory=lambda: ["prompt", "input", "query", "user", "user_message"])


@dataclass
class Config:
    include: List[str] = field(default_factory=lambda: list(DEFAULT_INCLUDES))
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    artifacts: List[ArtifactOverride] = field(default_factory=list)
    disabled_rules: List[str] = field(default_factory=list)
    rule_severities: Dict[str, str] = field(default_factory=dict)
    fail_on: str = DEFAULT_FAIL_ON
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    similarity: SimilarityConfig = field(default_factory=SimilarityConfig)
    config_path: Optional[str] = None


def _parse_artifact_schema(
    schema_data: Any,
    artifact_path: str,
    roles: List[str],
    artifact_index: int,
) -> ArtifactSchemaContract:
    if not isinstance(schema_data, dict):
        raise ConfigError(f"Artifact schema at index {artifact_index} must be an object.")
    for key in schema_data:
        if key not in {"required", "fields"}:
            raise ConfigError(f"Invalid key under artifact schema at index {artifact_index}: '{key}'.")

    if not roles or not set(roles).issubset(DATASET_SCHEMA_ROLES):
        raise ConfigError("Artifact schemas may only be assigned to dataset artifact roles.")

    extension = Path(artifact_path).suffix.lower()
    if extension not in SCHEMA_FORMAT_EXTENSIONS:
        raise ConfigError("Artifact schemas require a structured dataset format.")

    fields_data = schema_data.get("fields")
    if not isinstance(fields_data, dict) or not fields_data:
        raise ConfigError("Artifact schema 'fields' must be a non-empty object.")

    fields: Dict[str, FieldContract] = {}
    for field_name, field_data in fields_data.items():
        if not isinstance(field_name, str) or not field_name or any(char in field_name for char in ".[]"):
            raise ConfigError("Artifact schema fields must use a non-empty top-level field name.")
        if not isinstance(field_data, dict):
            raise ConfigError(f"Schema field '{field_name}' must be an object.")
        for key in field_data:
            if key not in {"type", "nullable"}:
                raise ConfigError(f"Invalid key for schema field '{field_name}': '{key}'.")

        field_type = field_data.get("type")
        if not isinstance(field_type, str) or field_type not in ALLOWED_SCHEMA_TYPES:
            raise ConfigError(f"Invalid schema field type for '{field_name}': '{field_type}'.")
        nullable = field_data.get("nullable", False)
        if not isinstance(nullable, bool):
            raise ConfigError(f"Schema field '{field_name}' nullable must be a boolean.")
        if extension == ".csv" and field_type != "string":
            raise ConfigError("CSV schema fields must use type 'string'.")
        fields[field_name] = FieldContract(type=field_type, nullable=nullable)

    required_data = schema_data.get("required", [])
    if not isinstance(required_data, list) or not all(isinstance(item, str) for item in required_data):
        raise ConfigError("Artifact schema 'required' must be a list of strings.")
    if len(required_data) != len(set(required_data)):
        raise ConfigError("Artifact schema 'required' must not contain duplicate field names.")
    for field_name in required_data:
        if field_name not in fields:
            raise ConfigError(
                f"Required schema field '{field_name}' must also be declared under 'fields'."
            )

    return ArtifactSchemaContract(required=list(required_data), fields=fields)


def _provenance_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("Provenance metadata values must be strings or null.")
    return value.strip() or None


def normalize_local_source_ref(value: str) -> str:
    path = value.replace("\\", "/")
    if path.startswith("/") or ":" in path or ".." in path.split("/") or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ConfigError("Local provenance source ref must be a safe scan-root-relative path.")
    return str(PurePosixPath(path))


def resolve_provenance_source(scan_root: str, ref: str) -> Path:
    root = Path(scan_root).resolve()
    target = (root / normalize_local_source_ref(ref)).resolve()
    if not target.is_relative_to(root):
        raise ConfigError("Local provenance source ref must stay inside the scan root.")
    return target


def _parse_artifact_provenance(data: Any, path: str, roles: List[str]) -> ArtifactProvenanceContract:
    if not isinstance(data, dict) or set(data) - {"required", "version", "fingerprint", "source", "generator", "license"}:
        raise ConfigError("Invalid provenance object or unknown provenance key.")
    if not roles or not set(roles).issubset(DATASET_SCHEMA_ROLES):
        raise ConfigError("Provenance contracts require dataset roles only.")
    if Path(path).suffix.lower() not in SCHEMA_FORMAT_EXTENSIONS | {".txt", ".text", ".md", ".markdown"}:
        raise ConfigError("Provenance contract requires a supported dataset format.")
    allowed = {"version", "fingerprint", "source.type", "source.ref", "source.revision", "generator.name", "generator.version", "license"}
    required = data.get("required", [])
    if not isinstance(required, list) or not all(isinstance(v, str) and v in allowed for v in required) or len(required) != len(set(required)):
        raise ConfigError("Provenance required must contain unique supported leaf names.")
    groups = {}
    for name, keys in [("source", {"type", "ref", "revision"}), ("generator", {"name", "version"})]:
        values = data.get(name)
        if values is None:
            values = {}
        if not isinstance(values, dict) or set(values) - keys:
            raise ConfigError("Invalid provenance metadata object or unknown key.")
        groups[name] = {key: _provenance_string(value) for key, value in values.items()}
    source = groups["source"]
    if source.get("type") not in {None, "local", "remote"}:
        raise ConfigError("Provenance source type must be local or remote.")
    if source.get("type") == "local" and source.get("ref"):
        # Inspect controls before trimming can erase a malformed path boundary.
        raw_ref = data["source"]["ref"]
        if any(ord(c) < 32 or ord(c) == 127 for c in raw_ref):
            raise ConfigError("Local provenance source ref contains control characters.")
        source["ref"] = normalize_local_source_ref(source["ref"])
    fingerprint = _provenance_string(data.get("fingerprint"))
    if fingerprint is not None:
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", fingerprint, re.IGNORECASE):
            raise ConfigError("Provenance fingerprint must be a SHA-256 hex digest.")
        fingerprint = "sha256:" + fingerprint.lower().removeprefix("sha256:")
    return ArtifactProvenanceContract(
        required=sorted(required), version=_provenance_string(data.get("version")),
        fingerprint=fingerprint, source=source, generator=groups["generator"],
        license=_provenance_string(data.get("license")),
    )


def parse_and_validate_config_dict(data: Any, config_path: Optional[str] = None) -> Config:
    if data is None:
        return Config(config_path=config_path)

    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a YAML object/dictionary.")

    # Check invalid top-level keys
    for key in data:
        if key not in ALLOWED_TOP_LEVEL_KEYS:
            raise ConfigError(f"Invalid top-level key in configuration: '{key}'.")

    cfg = Config(config_path=config_path)

    # 1. include
    if "include" in data:
        inc = data["include"]
        if not isinstance(inc, list) or not all(isinstance(x, str) for x in inc):
            raise ConfigError("'include' must be a list of strings.")
        cfg.include = list(inc)

    # 2. exclude
    if "exclude" in data:
        exc = data["exclude"]
        if not isinstance(exc, list) or not all(isinstance(x, str) for x in exc):
            raise ConfigError("'exclude' must be a list of strings.")
        cfg.exclude = list(exc)

    # 3. artifacts
    if "artifacts" in data:
        arts = data["artifacts"]
        if not isinstance(arts, list):
            raise ConfigError("'artifacts' must be a list of objects.")
        cfg.artifacts = []
        seen_artifact_paths: Set[str] = set()
        for idx, item in enumerate(arts):
            if not isinstance(item, dict) or "path" not in item or "roles" not in item:
                raise ConfigError(f"Artifact entry at index {idx} must be an object with 'path' and 'roles'.")
            for key in item:
                if key not in {"path", "roles", "schema", "provenance"}:
                    raise ConfigError(f"Invalid key in artifact entry at index {idx}: '{key}'.")
            path_val = item["path"]
            roles_val = item["roles"]
            if not isinstance(path_val, str):
                raise ConfigError(f"Artifact entry path at index {idx} must be a string.")
            if not isinstance(roles_val, list) or not all(isinstance(r, str) for r in roles_val):
                raise ConfigError(f"Artifact entry roles at index {idx} must be a list of strings.")
            for r in roles_val:
                if r not in ALLOWED_ROLES:
                    raise ConfigError(f"Invalid artifact role '{r}' in artifact entry at index {idx}.")
            # Normalize path separator to POSIX
            posix_path = path_val.replace("\\", "/")
            if posix_path.startswith("./"):
                posix_path = posix_path[2:]
            if posix_path in seen_artifact_paths:
                raise ConfigError(f"Duplicate artifact path in configuration: '{posix_path}'.")
            seen_artifact_paths.add(posix_path)

            schema = None
            if "schema" in item:
                schema = _parse_artifact_schema(item["schema"], posix_path, roles_val, idx)
            provenance = _parse_artifact_provenance(item["provenance"], posix_path, roles_val) if "provenance" in item else None
            cfg.artifacts.append(ArtifactOverride(path=posix_path, roles=roles_val, schema=schema, provenance=provenance))

    # 4. rules
    if "rules" in data:
        rules_data = data["rules"]
        if not isinstance(rules_data, dict):
            raise ConfigError("'rules' must be an object.")
        for key in rules_data:
            if key not in {"disabled", "severity"}:
                raise ConfigError(f"Invalid key under 'rules': '{key}'.")

        if "disabled" in rules_data:
            dis = rules_data["disabled"]
            if not isinstance(dis, list) or not all(isinstance(x, str) for x in dis):
                raise ConfigError("'rules.disabled' must be a list of strings.")
            cfg.disabled_rules = list(dis)

        if "severity" in rules_data:
            sev_map = rules_data["severity"]
            if not isinstance(sev_map, dict):
                raise ConfigError("'rules.severity' must be an object/dictionary.")
            for rule_id, sev_val in sev_map.items():
                if not isinstance(rule_id, str) or not isinstance(sev_val, str):
                    raise ConfigError("'rules.severity' keys and values must be strings.")
                if sev_val not in ALLOWED_SEVERITIES:
                    raise ConfigError(f"Invalid severity '{sev_val}' for rule '{rule_id}'.")
                cfg.rule_severities[rule_id] = sev_val

    # 5. ci
    if "ci" in data:
        ci_data = data["ci"]
        if not isinstance(ci_data, dict):
            raise ConfigError("'ci' must be an object.")
        for key in ci_data:
            if key != "fail_on":
                raise ConfigError(f"Invalid key under 'ci': '{key}'.")
        if "fail_on" in ci_data:
            fail_val = ci_data["fail_on"]
            if not isinstance(fail_val, str) or fail_val not in ALLOWED_SEVERITIES:
                raise ConfigError(f"Invalid 'ci.fail_on' severity value: '{fail_val}'.")
            cfg.fail_on = fail_val

    # 6. limits
    if "limits" in data:
        lim_data = data["limits"]
        if not isinstance(lim_data, dict):
            raise ConfigError("'limits' must be an object.")
        for key in lim_data:
            if key not in {"max_file_mb", "max_rows_per_artifact"}:
                raise ConfigError(f"Invalid key under 'limits': '{key}'.")

        if "max_file_mb" in lim_data:
            val = lim_data["max_file_mb"]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ConfigError("'limits.max_file_mb' must be a positive integer.")
            cfg.limits.max_file_mb = val

        if "max_rows_per_artifact" in lim_data:
            val = lim_data["max_rows_per_artifact"]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ConfigError("'limits.max_rows_per_artifact' must be a positive integer.")
            cfg.limits.max_rows_per_artifact = val

    # 7. similarity
    if "similarity" in data:
        sim_data = data["similarity"]
        if not isinstance(sim_data, dict):
            raise ConfigError("'similarity' must be an object.")
        for key in sim_data:
            if key not in {"enabled", "shingle_size", "num_hashes", "bands", "threshold", "focus_roles", "focus_fields"}:
                raise ConfigError(f"Invalid key under 'similarity': '{key}'.")

        if "enabled" in sim_data:
            val = sim_data["enabled"]
            if not isinstance(val, bool):
                raise ConfigError("'similarity.enabled' must be a boolean.")
            cfg.similarity.enabled = val

        if "shingle_size" in sim_data:
            val = sim_data["shingle_size"]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ConfigError("'similarity.shingle_size' must be a positive integer.")
            cfg.similarity.shingle_size = val

        if "num_hashes" in sim_data:
            val = sim_data["num_hashes"]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ConfigError("'similarity.num_hashes' must be a positive integer.")
            cfg.similarity.num_hashes = val

        if "bands" in sim_data:
            val = sim_data["bands"]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ConfigError("'similarity.bands' must be a positive integer.")
            cfg.similarity.bands = val

        if "threshold" in sim_data:
            val = sim_data["threshold"]
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not (0.0 <= val <= 1.0):
                raise ConfigError("'similarity.threshold' must be a float between 0.0 and 1.0.")
            cfg.similarity.threshold = float(val)

        if "focus_roles" in sim_data:
            val = sim_data["focus_roles"]
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                raise ConfigError("'similarity.focus_roles' must be a list of strings.")
            cfg.similarity.focus_roles = list(val)

        if "focus_fields" in sim_data:
            val = sim_data["focus_fields"]
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                raise ConfigError("'similarity.focus_fields' must be a list of strings.")
            cfg.similarity.focus_fields = list(val)

    return cfg


def load_config(scan_root: str, explicit_config_path: Optional[str] = None) -> Config:
    """Load configuration from explicit path or default evalproof.yaml in scan root."""
    scan_root_path = Path(scan_root)

    if explicit_config_path:
        target_path = Path(explicit_config_path)
        if not target_path.is_absolute():
            target_path = scan_root_path / target_path
        if not target_path.exists() or not target_path.is_file():
            raise ConfigError(f"Config file not found: {explicit_config_path}")
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except Exception as err:
            raise ConfigError(f"Failed to parse config file '{explicit_config_path}': {err}") from err
        rel_config_path = str(target_path.relative_to(scan_root_path)).replace("\\", "/") if target_path.is_relative_to(scan_root_path) else str(target_path)
        return parse_and_validate_config_dict(content, config_path=rel_config_path)

    # Default lookup: evalproof.yaml or evalproof.yml
    for name in ["evalproof.yaml", "evalproof.yml"]:
        candidate = scan_root_path / name
        if candidate.exists() and candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
            except Exception as err:
                raise ConfigError(f"Failed to parse default config file '{name}': {err}") from err
            return parse_and_validate_config_dict(content, config_path=name)

    # No config file found; return default config
    return Config(config_path=None)


def validate_schema_artifact_paths(scan_root: str, config: Config) -> None:
    """Ensure explicit schema/provenance contracts cannot be silently skipped."""
    from evalproof.discovery import is_pattern_matched

    root = Path(scan_root).resolve()
    for override in config.artifacts:
        if override.schema is None and override.provenance is None:
            continue
        label = "Schema" if override.schema is not None else "Provenance"
        target = (root / override.path).resolve()
        if not target.is_relative_to(root):
            raise ConfigError(
                f"{label} artifact path must stay inside the scan root: '{override.path}'."
            )
        if not target.exists() or not target.is_file():
            raise ConfigError(f"{label} artifact path does not exist: '{override.path}'.")
        if is_pattern_matched(override.path, config.exclude):
            raise ConfigError(
                f"{label} artifact path is excluded from discovery: '{override.path}'."
            )
        if not is_pattern_matched(override.path, config.include):
            raise ConfigError(
                f"{label} artifact path is not included in discovery: '{override.path}'."
            )
        if override.provenance is not None:
            source = override.provenance.source
            if source.get("type") == "local" and source.get("ref"):
                try:
                    resolve_provenance_source(scan_root, source["ref"])
                except (OSError, RuntimeError):
                    pass  # Index records unobservable sources without claiming absence.
