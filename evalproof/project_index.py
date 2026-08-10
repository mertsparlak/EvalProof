"""Project Index for derived, deterministic cross-artifact facts and indexing."""

import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Any, Tuple
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from evalproof.artifact import Artifact
from evalproof.config import Config
from evalproof.finding import Diagnostic, DiagnosticSeverity, DiagnosticCode, canonical_json_dumps
from evalproof.similarity import SimilarityIndex, extract_target_similarity_text


TRIVIAL_LABELS: Set[str] = {"yes", "no", "true", "false"}

ANSWER_FIELD_ALIASES: List[str] = [
    "answer",
    "expected",
    "expected_answer",
    "gold",
    "gold_answer",
    "label",
    "reference",
    "reference_answer",
]

CANONICAL_METADATA_ALIASES: Dict[str, List[str]] = {
    "model_id": ["model", "model_id", "model_name"],
    "generation_parameters": ["generation_parameters", "generation_params", "parameters", "params"],
    "prompt_fingerprint": ["prompt_fingerprint", "prompt_hash", "prompt_sha256"],
    "prompt_version": ["prompt_version", "prompt_id"],
    "dataset_fingerprint": ["dataset_fingerprint", "dataset_hash", "dataset_sha256"],
    "dataset_version": ["dataset_version", "dataset_id"],
    "metric_name": ["metric", "metric_name"],
    "metric_definition": ["metric_definition", "metric_description"],
    "metric_threshold": ["threshold", "pass_threshold", "metric_threshold"],
    "timestamp": ["timestamp", "created_at", "evaluated_at"],
}


def normalize_plain_text(text: str) -> str:
    """Plain text normalization for containment checks:
    - line endings normalize to \\n
    - leading/trailing whitespace trimmed
    - internal consecutive whitespace collapsed to single ASCII space
    - case preserved
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"[ \t\n]+", " ", text)


def normalize_row_data(val: Any) -> Any:
    """Trim surrounding whitespace in string fields recursively for row normalization."""
    if isinstance(val, str):
        return val.strip()
    elif isinstance(val, dict):
        return {k: normalize_row_data(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [normalize_row_data(item) for item in val]
    return val


def compute_row_hash(row_obj: Any) -> str:
    """Produce stable sha256 hash of normalized row object."""
    norm_obj = normalize_row_data(row_obj)
    canonical_str = canonical_json_dumps(norm_obj)
    digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_trivial_answer(val_str: str) -> bool:
    """Check if string is a trivial label ignored by RAG answer extraction."""
    norm = val_str.strip().lower()
    if norm in TRIVIAL_LABELS:
        return True
    if len(norm) == 1 and (norm.isalpha() or norm.isdigit()):
        return True
    return False


@dataclass
class RowRecord:
    artifact_path: str
    row_num: int
    row_data: Any
    row_hash: str


@dataclass
class AnswerRecord:
    artifact_path: str
    row_num: int
    field_name: str
    raw_answer: str
    normalized_answer: str


class ProjectIndex:
    def __init__(self, config: Config):
        self.config = config
        self.artifacts_by_path: Dict[str, Artifact] = {}
        self.artifacts_by_role: Dict[str, List[Artifact]] = {}
        self.rows_by_artifact: Dict[str, List[RowRecord]] = {}
        self.record_hashes: Dict[str, List[Tuple[str, int]]] = {}  # hash -> [(path, row_num)]
        self.answer_records: List[AnswerRecord] = []
        self.artifact_fingerprints: Dict[str, str] = {}
        self.eval_metadata: Dict[str, Dict[str, Any]] = {}
        self.diagnostics: List[Diagnostic] = []

        # Similarity Index for Near-Duplicate Detection
        sim_cfg = config.similarity
        self.similarity_index = SimilarityIndex(
            shingle_size=sim_cfg.shingle_size,
            num_hashes=sim_cfg.num_hashes,
            bands=sim_cfg.bands,
            threshold=sim_cfg.threshold,
        )

    def build(self, artifacts: List[Artifact]):
        """Index derived facts across all candidate artifacts."""
        for art in artifacts:
            self.artifacts_by_path[art.path] = art
            for r in art.roles:
                self.artifacts_by_role.setdefault(r, []).append(art)

            # Check file size limit
            if art.full_disk_path and os.path.exists(art.full_disk_path):
                file_size_bytes = os.path.getsize(art.full_disk_path)
                max_bytes = self.config.limits.max_file_mb * 1024 * 1024
                if file_size_bytes > max_bytes:
                    diag = Diagnostic(
                        severity=DiagnosticSeverity.WARNING.value,
                        code=DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value,
                        message=f"File size ({file_size_bytes} bytes) exceeds limit ({self.config.limits.max_file_mb} MB). Skipped indexing.",
                        path=art.path,
                        details={
                            "limit_name": "limits.max_file_mb",
                            "configured_limit": self.config.limits.max_file_mb,
                            "observed_size": file_size_bytes,
                        },
                    )
                    self.diagnostics.append(diag)
                    art.diagnostics.append(diag)
                    continue

            # Process artifact content and fingerprints
            self._index_artifact_content(art)

    def _index_artifact_content(self, art: Artifact):
        text = art.read_text()

        # Markdown & Plain text
        if art.format in {"markdown", "plain_text"}:
            norm_text = text.replace("\r\n", "\n").replace("\r", "\n")
            digest = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
            self.artifact_fingerprints[art.path] = f"sha256:{digest}"
            return

        # Structured formats: JSON, JSONL, CSV, YAML, TOML
        if art.format == "jsonl":
            self._index_jsonl(art, text)
        elif art.format == "csv":
            self._index_csv(art, text)
        elif art.format == "json":
            self._index_json(art, text)
        elif art.format == "yaml":
            self._index_yaml(art, text)
        elif art.format == "toml":
            self._index_toml(art, text)

    def _index_jsonl(self, art: Artifact, text: str):
        lines = text.splitlines()
        valid_rows: List[RowRecord] = []
        normalized_row_json_strings: List[str] = []
        limit_reached = False

        for idx, line in enumerate(lines, start=1):
            s_line = line.strip()
            if not s_line:
                continue

            try:
                parsed = json.loads(s_line)
            except Exception as err:
                diag = Diagnostic(
                    severity=DiagnosticSeverity.WARNING.value,
                    code=DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
                    message=f"Failed to parse row {idx} as JSONL.",
                    path=art.path,
                    row=idx,
                    details={"format": "jsonl", "error": str(err)},
                )
                self.diagnostics.append(diag)
                art.diagnostics.append(diag)
                continue

            if len(valid_rows) >= self.config.limits.max_rows_per_artifact:
                if not limit_reached:
                    limit_reached = True
                    diag = Diagnostic(
                        severity=DiagnosticSeverity.WARNING.value,
                        code=DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
                        message=f"Row count reached configured limit of {self.config.limits.max_rows_per_artifact}.",
                        path=art.path,
                        row=idx,
                        details={
                            "limit_name": "limits.max_rows_per_artifact",
                            "configured_limit": self.config.limits.max_rows_per_artifact,
                        },
                    )
                    self.diagnostics.append(diag)
                    art.diagnostics.append(diag)
                break

            r_hash = compute_row_hash(parsed)
            rec = RowRecord(artifact_path=art.path, row_num=idx, row_data=parsed, row_hash=r_hash)
            valid_rows.append(rec)
            self.record_hashes.setdefault(r_hash, []).append((art.path, idx))
            normalized_row_json_strings.append(canonical_json_dumps(normalize_row_data(parsed)))

            # Index into Similarity Engine
            self._index_row_for_similarity(art, idx, parsed, r_hash)

            # Check answer extraction
            self._check_answer_extraction(art, idx, parsed)

        self.rows_by_artifact[art.path] = valid_rows
        # Fingerprint is normalized rows joined by newline
        joined = "\n".join(normalized_row_json_strings)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        self.artifact_fingerprints[art.path] = f"sha256:{digest}"

    def _index_csv(self, art: Artifact, text: str):
        if not text.strip():
            return

        f_in = io.StringIO(text)
        reader = csv.reader(f_in)

        try:
            header = next(reader, None)
        except Exception as err:
            diag = Diagnostic(
                severity=DiagnosticSeverity.WARNING.value,
                code=DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
                message=f"Could not parse CSV header: {err}",
                path=art.path,
            )
            self.diagnostics.append(diag)
            art.diagnostics.append(diag)
            return

        if not header:
            return

        clean_header = [h.strip() for h in header]
        expected_len = len(clean_header)
        valid_rows: List[RowRecord] = []
        normalized_row_json_strings: List[str] = []
        limit_reached = False

        for row_idx, row in enumerate(reader, start=2):
            if len(row) != expected_len:
                diag = Diagnostic(
                    severity=DiagnosticSeverity.WARNING.value,
                    code=DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
                    message=f"Row {row_idx} field count ({len(row)}) does not match header count ({expected_len}).",
                    path=art.path,
                    row=row_idx,
                )
                self.diagnostics.append(diag)
                art.diagnostics.append(diag)
                continue

            if len(valid_rows) >= self.config.limits.max_rows_per_artifact:
                if not limit_reached:
                    limit_reached = True
                    diag = Diagnostic(
                        severity=DiagnosticSeverity.WARNING.value,
                        code=DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
                        message=f"Row count reached configured limit of {self.config.limits.max_rows_per_artifact}.",
                        path=art.path,
                        row=row_idx,
                    )
                    self.diagnostics.append(diag)
                    art.diagnostics.append(diag)
                break

            parsed_obj = {clean_header[i]: row[i].strip() for i in range(expected_len)}
            r_hash = compute_row_hash(parsed_obj)
            rec = RowRecord(artifact_path=art.path, row_num=row_idx, row_data=parsed_obj, row_hash=r_hash)
            valid_rows.append(rec)
            self.record_hashes.setdefault(r_hash, []).append((art.path, row_idx))
            normalized_row_json_strings.append(canonical_json_dumps(normalize_row_data(parsed_obj)))

            # Index into Similarity Engine
            self._index_row_for_similarity(art, row_idx, parsed_obj, r_hash)

            # Check answer extraction
            self._check_answer_extraction(art, row_idx, parsed_obj)

        self.rows_by_artifact[art.path] = valid_rows
        joined = "\n".join(normalized_row_json_strings)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        self.artifact_fingerprints[art.path] = f"sha256:{digest}"

    def _index_json(self, art: Artifact, text: str):
        try:
            data = json.loads(text)
        except Exception as err:
            diag = Diagnostic(
                severity=DiagnosticSeverity.WARNING.value,
                code=DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
                message=f"Could not parse JSON artifact: {err}",
                path=art.path,
            )
            self.diagnostics.append(diag)
            art.diagnostics.append(diag)
            return

        canonical_str = canonical_json_dumps(data)
        digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        self.artifact_fingerprints[art.path] = f"sha256:{digest}"

        self._extract_json_rows_and_metadata(art, data)

    def _index_yaml(self, art: Artifact, text: str):
        try:
            data = yaml.safe_load(text)
        except Exception as err:
            diag = Diagnostic(
                severity=DiagnosticSeverity.WARNING.value,
                code=DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
                message=f"Could not parse YAML artifact: {err}",
                path=art.path,
            )
            self.diagnostics.append(diag)
            art.diagnostics.append(diag)
            return

        if data is not None:
            canonical_str = canonical_json_dumps(data)
            digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            self.artifact_fingerprints[art.path] = f"sha256:{digest}"
            self._extract_json_rows_and_metadata(art, data)

    def _index_toml(self, art: Artifact, text: str):
        try:
            data = tomllib.loads(text)
        except Exception as err:
            diag = Diagnostic(
                severity=DiagnosticSeverity.WARNING.value,
                code=DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
                message=f"Could not parse TOML artifact: {err}",
                path=art.path,
            )
            self.diagnostics.append(diag)
            art.diagnostics.append(diag)
            return

        if data is not None:
            canonical_str = canonical_json_dumps(data)
            digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            self.artifact_fingerprints[art.path] = f"sha256:{digest}"
            self._extract_json_rows_and_metadata(art, data)

    def _extract_json_rows_and_metadata(self, art: Artifact, data: Any):
        # Extract metadata if evaluation_result role
        if "evaluation_result" in art.roles:
            meta = self.extract_result_metadata(data)
            if meta:
                self.eval_metadata[art.path] = meta

        # Row extraction
        rows_list: Optional[List[Any]] = None
        if isinstance(data, list):
            rows_list = data
        elif isinstance(data, dict):
            for field_key in ["examples", "samples", "records", "rows", "data", "items"]:
                if field_key in data and isinstance(data[field_key], list):
                    rows_list = data[field_key]
                    break

        if rows_list is not None:
            valid_rows: List[RowRecord] = []
            limit_reached = False
            for idx, item in enumerate(rows_list, start=1):
                if len(valid_rows) >= self.config.limits.max_rows_per_artifact:
                    if not limit_reached:
                        limit_reached = True
                        diag = Diagnostic(
                            severity=DiagnosticSeverity.WARNING.value,
                            code=DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
                            message=f"Row count reached configured limit of {self.config.limits.max_rows_per_artifact}.",
                            path=art.path,
                            row=idx,
                        )
                        self.diagnostics.append(diag)
                        art.diagnostics.append(diag)
                    break

                r_hash = compute_row_hash(item)
                rec = RowRecord(artifact_path=art.path, row_num=idx, row_data=item, row_hash=r_hash)
                valid_rows.append(rec)
                self.record_hashes.setdefault(r_hash, []).append((art.path, idx))
                self._index_row_for_similarity(art, idx, item, r_hash)
                self._check_answer_extraction(art, idx, item)

            self.rows_by_artifact[art.path] = valid_rows

    def _index_row_for_similarity(self, art: Artifact, row_num: int, row_data: Any, r_hash: str):
        """Index dataset row text into Similarity Engine for near-duplicate checks."""
        if not self.config.similarity.enabled:
            return
        row_str = extract_target_similarity_text(row_data, self.config.similarity)
        item_id = f"{art.path}:row:{row_num}"
        self.similarity_index.add_item(
            item_id=item_id,
            text=row_str,
            metadata={
                "path": art.path,
                "row_number": row_num,
                "roles": list(art.roles),
                "exact_hash": r_hash,
            },
        )

    def _check_answer_extraction(self, art: Artifact, row_num: int, row_data: Any):
        """Check if structured row has answer-like fields for RAG answer leakage."""
        if not isinstance(row_data, dict):
            return

        for alias in ANSWER_FIELD_ALIASES:
            if alias in row_data:
                val = row_data[alias]
                if val is None:
                    continue
                val_str = str(val).strip()
                if not val_str:
                    continue
                norm = normalize_plain_text(val_str)
                # Ignore if < 16 chars or trivial label
                if len(norm) < 16 or is_trivial_answer(val_str):
                    continue

                self.answer_records.append(
                    AnswerRecord(
                        artifact_path=art.path,
                        row_num=row_num,
                        field_name=alias,
                        raw_answer=val_str,
                        normalized_answer=norm,
                    )
                )
                break  # match first alias

    def extract_result_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract canonical evaluation result metadata fields."""
        if not isinstance(data, dict):
            return {}

        result_meta: Dict[str, Any] = {}

        # Sub-objects to check in addition to top-level
        sub_sources = [data]
        for sub_key in ["metadata", "eval", "evaluation", "run"]:
            if sub_key in data and isinstance(data[sub_key], dict):
                sub_sources.append(data[sub_key])

        for canonical_name, aliases in CANONICAL_METADATA_ALIASES.items():
            found_val = None
            for src in sub_sources:
                for alias in aliases:
                    if alias in src and src[alias] is not None:
                        found_val = src[alias]
                        break
                if found_val is not None:
                    break
            if found_val is not None:
                result_meta[canonical_name] = found_val

        return result_meta
