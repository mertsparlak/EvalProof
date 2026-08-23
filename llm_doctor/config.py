"""Configuration loading, validation, and schema definitions."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import yaml

from llm_doctor.finding import Severity


ALLOWED_TOP_LEVEL_KEYS: Set[str] = {
    "include",
    "exclude",
    "artifacts",
    "rules",
    "ci",
    "limits",
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
]

DEFAULT_FAIL_ON: str = Severity.HIGH.value
DEFAULT_MAX_FILE_MB: int = 50
DEFAULT_MAX_ROWS_PER_ARTIFACT: int = 250000


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass
class ArtifactOverride:
    path: str
    roles: List[str]


@dataclass
class LimitsConfig:
    max_file_mb: int = DEFAULT_MAX_FILE_MB
    max_rows_per_artifact: int = DEFAULT_MAX_ROWS_PER_ARTIFACT


@dataclass
class Config:
    include: List[str] = field(default_factory=lambda: list(DEFAULT_INCLUDES))
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    artifacts: List[ArtifactOverride] = field(default_factory=list)
    disabled_rules: List[str] = field(default_factory=list)
    rule_severities: Dict[str, str] = field(default_factory=dict)
    fail_on: str = DEFAULT_FAIL_ON
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    config_path: Optional[str] = None


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
        for idx, item in enumerate(arts):
            if not isinstance(item, dict) or "path" not in item or "roles" not in item:
                raise ConfigError(f"Artifact entry at index {idx} must be an object with 'path' and 'roles'.")
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
            cfg.artifacts.append(ArtifactOverride(path=posix_path, roles=roles_val))

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
