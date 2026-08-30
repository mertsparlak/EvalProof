"""Project Index for derived, deterministic cross-artifact facts and indexing."""

import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import math
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
from evalproof.similarity import SimilarityCandidate, SimilarityIndex, extract_target_similarity_text


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

INPUT_FIELD_ALIASES: List[str] = ["prompt", "question", "input"]
RAG_CONTENT_FIELD_ALIASES: List[str] = ["text", "content", "document", "body", "chunk", "page_content"]

SAMPLE_ID_FIELD_ALIASES: List[str] = ["id", "sample_id", "example_id", "record_id", "case_id"]
CONTEXT_ID_SCALAR_FIELD_ALIASES: List[str] = ["doc_id", "document_id", "context_id", "source_id", "chunk_id"]
RAG_ID_SCALAR_FIELD_ALIASES: List[str] = ["id", "doc_id", "document_id", "context_id", "source_id", "chunk_id"]
CONTEXT_ID_LIST_FIELD_ALIASES: List[str] = ["doc_ids", "document_ids", "context_ids", "source_ids", "chunk_ids", "retrieved_context_ids"]
CONTEXT_FIELD_ALIASES: List[str] = [
    "context",
    "contexts",
    "documents",
    "docs",
    "retrieved_context",
    "retrieval_context",
    "sources",
    "chunks",
]
SIMILARITY_DISCRIMINATOR_ALIASES: Set[str] = set(CONTEXT_FIELD_ALIASES + ANSWER_FIELD_ALIASES)
ROW_COLLECTION_KEYS: List[str] = ["examples", "samples", "records", "rows", "data", "items"]
KNOWN_METRIC_NAMES: Set[str] = {
    "accuracy",
    "accuracy_percent",
    "exact_match",
    "f1",
    "precision",
    "recall",
    "bleu",
    "rouge",
    "loss",
    "perplexity",
    "pass_rate",
    "success_rate",
    "win_rate",
}

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


def compute_similarity_discriminator(row_obj: Any) -> Optional[str]:
    """Hash explicit context/target fields used to disambiguate eval rows."""
    if not isinstance(row_obj, dict):
        return None

    discriminator: Dict[str, Any] = {}
    for key, value in sorted(row_obj.items(), key=lambda item: str(item[0]).lower()):
        normalized_key = str(key).lower()
        if normalized_key not in SIMILARITY_DISCRIMINATOR_ALIASES:
            continue
        normalized_value = normalize_row_data(value)
        if normalized_value is None or normalized_value == "" or normalized_value == [] or normalized_value == {}:
            continue
        discriminator[normalized_key] = normalized_value

    if not discriminator:
        return None
    digest = hashlib.sha256(canonical_json_dumps(discriminator).encode("utf-8")).hexdigest()
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


@dataclass(frozen=True)
class RagChunkRecord:
    artifact_path: str
    row_num: int
    row_hash: str
    chunk_id_hash: str
    content_field: str
    content_hash: str


@dataclass(frozen=True)
class ContextReference:
    field_name: str
    value: str
    value_hash: str


@dataclass
class MetricRecord:
    artifact_path: str
    metric_name: str
    value: float
    unit: Optional[str]
    bounds: List[float]
    field_path: str



def normalize_context_identifier(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    normalized = str(value).strip()
    return normalized or None


def extract_context_references(row_data: Any, include_lists: bool = True, include_generic_id: bool = False) -> List[ContextReference]:
    if not isinstance(row_data, dict):
        return []

    references: List[ContextReference] = []

    def append_reference(field_name: str, value: Any) -> None:
        normalized = normalize_context_identifier(value)
        if normalized is None:
            return
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        references.append(ContextReference(field_name=field_name, value=normalized, value_hash=f"sha256:{digest}"))

    scalar_aliases = RAG_ID_SCALAR_FIELD_ALIASES if include_generic_id else CONTEXT_ID_SCALAR_FIELD_ALIASES
    for field_name in scalar_aliases:
        if field_name in row_data:
            append_reference(field_name, row_data[field_name])

    if include_lists:
        for field_name in CONTEXT_ID_LIST_FIELD_ALIASES:
            values = row_data.get(field_name)
            if not isinstance(values, list):
                continue
            for value in values:
                append_reference(field_name, value)

    return references

def normalize_fingerprint(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized.startswith("sha256:"):
        return normalized[7:]
    return normalized


def extract_rag_content(row_data: Any) -> Optional[Tuple[str, str]]:
    """Return the first supported non-empty top-level RAG content value."""
    if not isinstance(row_data, dict):
        return None
    for field_name in RAG_CONTENT_FIELD_ALIASES:
        value = row_data.get(field_name)
        if isinstance(value, str) and value.strip():
            return field_name, normalize_plain_text(value)
    return None


def extract_scalar_field(row_data: Any, aliases: List[str]) -> Optional[Tuple[str, str]]:
    if not isinstance(row_data, dict):
        return None
    for alias in aliases:
        if alias not in row_data:
            continue
        value = row_data[alias]
        if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
            continue
        normalized = str(value).strip()
        if normalized:
            return alias, normalized
    return None


def extract_target_values(row_data: Any, aliases: List[str]) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """Extract a canonical target as a deterministic set of scalar values."""
    if not isinstance(row_data, dict):
        return None

    for alias in aliases:
        if alias not in row_data:
            continue
        raw_values = row_data[alias] if isinstance(row_data[alias], list) else [row_data[alias]]
        normalized_values = set()
        for value in raw_values:
            if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
                continue
            normalized = normalize_plain_text(str(value))
            if normalized:
                normalized_values.add(normalized)
        if normalized_values:
            return alias, tuple(sorted(normalized_values))
    return None


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
        self.metric_records: List[MetricRecord] = []
        self.diagnostics: List[Diagnostic] = []
        self._similarity_candidates_cache: Dict[float, List[SimilarityCandidate]] = {}

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
        self._similarity_candidates_cache.clear()
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

    def get_similarity_candidates(self, threshold: Optional[float] = None) -> List[SimilarityCandidate]:
        """Return cached near-duplicate candidates for the requested threshold."""
        resolved_threshold = self.config.similarity.threshold if threshold is None else float(threshold)
        if resolved_threshold not in self._similarity_candidates_cache:
            self._similarity_candidates_cache[resolved_threshold] = self.similarity_index.find_all_pairs(
                threshold=resolved_threshold
            )
        return self._similarity_candidates_cache[resolved_threshold]

    def get_artifact_coverage(self, active_rules: List[Any]) -> List[Dict[str, Any]]:
        """Return deterministic, report-safe coverage metadata for indexed artifacts."""
        coverage: List[Dict[str, Any]] = []
        diagnostics_by_path: Dict[str, List[Diagnostic]] = {}
        for diagnostic in self.diagnostics:
            if diagnostic.path:
                diagnostics_by_path.setdefault(diagnostic.path, []).append(diagnostic)

        for path in sorted(self.artifacts_by_path):
            artifact = self.artifacts_by_path[path]
            path_diagnostics = []
            seen_diagnostic_ids: Set[int] = set()
            for diagnostic in diagnostics_by_path.get(path, []) + list(artifact.diagnostics):
                if id(diagnostic) in seen_diagnostic_ids:
                    continue
                seen_diagnostic_ids.add(id(diagnostic))
                path_diagnostics.append(diagnostic)
            diagnostic_codes = sorted({diagnostic.code for diagnostic in path_diagnostics})
            rejected_rows = sum(
                1
                for diagnostic in path_diagnostics
                if diagnostic.code == DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value
            )
            truncated = any(
                diagnostic.code == DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value
                for diagnostic in path_diagnostics
            )
            has_file_size_limit = any(
                diagnostic.code == DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value
                for diagnostic in path_diagnostics
            )
            has_parse_failure = any(
                diagnostic.code == DiagnosticCode.ARTIFACT_PARSE_FAILED.value
                for diagnostic in path_diagnostics
            )
            has_row_partial = rejected_rows > 0 or truncated
            fingerprint = self.artifact_fingerprints.get(path)
            rows_indexed = len(self.rows_by_artifact[path]) if path in self.rows_by_artifact else None

            if has_file_size_limit or (has_parse_failure and fingerprint is None) or fingerprint is None:
                index_status = "skipped"
                reasons = []
                if has_file_size_limit:
                    reasons.append("file_size_limit")
                if has_parse_failure:
                    reasons.append("parse_failed")
                if not reasons:
                    reasons.append("no_indexable_content")
            elif has_row_partial:
                index_status = "partial"
                reasons = []
                if rejected_rows > 0:
                    reasons.append("row_parse_failures")
                if truncated:
                    reasons.append("row_limit")
            else:
                index_status = "indexed"
                reasons = ["complete"]

            role_matched_rule_ids = sorted(
                rule.id
                for rule in active_rules
                if set(rule.artifact_roles).intersection(artifact.roles)
            )
            coverage.append(
                {
                    "path": path,
                    "format": artifact.format,
                    "roles": sorted(artifact.roles),
                    "role_source": artifact.role_source,
                    "index_status": index_status,
                    "index_reasons": reasons,
                    "rows_indexed": rows_indexed,
                    "rows_rejected": rejected_rows,
                    "truncated": truncated,
                    "fingerprint": fingerprint,
                    "diagnostic_codes": diagnostic_codes,
                    "role_matched_rule_ids": role_matched_rule_ids,
                }
            )
        return coverage

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
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
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
            self._extract_metric_records_from_source(art, parsed, f"rows[{idx}]")

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
            self._extract_metric_records_from_source(art, parsed_obj, f"rows[{row_idx}]")

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
            self._extract_metric_records_from_source(art, data, "")

        # Row extraction
        rows_list: Optional[List[Any]] = None
        rows_field_key = "root"
        if isinstance(data, list):
            rows_list = data
        elif isinstance(data, dict):
            for field_key in ROW_COLLECTION_KEYS:
                if field_key in data and isinstance(data[field_key], list):
                    rows_list = data[field_key]
                    rows_field_key = field_key
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
                self._extract_metric_records_from_source(art, item, f"{rows_field_key}[{idx}]")

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
                "similarity_discriminator": compute_similarity_discriminator(row_data),
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

    def get_context_references(self, roles: Set[str], include_lists: bool = True, include_generic_id: bool = False) -> List[Tuple[RowRecord, ContextReference]]:
        """Return explicit context ID references from rows with selected artifact roles."""
        references: List[Tuple[RowRecord, ContextReference]] = []
        for artifact_path in sorted(self.rows_by_artifact):
            artifact = self.artifacts_by_path.get(artifact_path)
            if artifact is None or not roles.intersection(artifact.roles):
                continue
            for row in self.rows_by_artifact[artifact_path]:
                for reference in extract_context_references(row.row_data, include_lists=include_lists, include_generic_id=include_generic_id):
                    references.append((row, reference))
        return references

    def get_rag_chunk_records(self) -> List[RagChunkRecord]:
        """Extract redacted, artifact-scoped explicit chunk identities."""
        incomplete_codes = {
            DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
            DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
            DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
            DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value,
        }
        incomplete_paths = {
            diagnostic.path for diagnostic in self.diagnostics
            if diagnostic.code in incomplete_codes
        }
        records = []
        for path, artifact in sorted(self.artifacts_by_path.items()):
            if "rag_document" not in artifact.roles or "configuration" in artifact.roles:
                continue
            if path in incomplete_paths or any(
                diagnostic.code in incomplete_codes for diagnostic in artifact.diagnostics
            ):
                continue
            for row in sorted(self.rows_by_artifact.get(path, []), key=lambda item: item.row_num):
                if not isinstance(row.row_data, dict):
                    continue
                chunk_id = normalize_context_identifier(row.row_data.get("chunk_id"))
                content = extract_rag_content(row.row_data)
                if chunk_id is None or content is None:
                    continue
                content_field, normalized_content = content
                records.append(RagChunkRecord(
                    artifact_path=path,
                    row_num=row.row_num,
                    row_hash=row.row_hash,
                    chunk_id_hash="sha256:" + hashlib.sha256(chunk_id.encode("utf-8")).hexdigest(),
                    content_field=content_field,
                    content_hash="sha256:" + hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
                ))
        return records

    def matching_artifacts_for_fingerprint(self, reference: Any, roles: Set[str]) -> List[Artifact]:
        normalized_reference = normalize_fingerprint(reference)
        matches = []
        for artifact in self.artifacts_by_path.values():
            if not roles.intersection(artifact.roles) or "configuration" in artifact.roles:
                continue
            computed = self.artifact_fingerprints.get(artifact.path)
            if computed and normalize_fingerprint(computed) == normalized_reference:
                matches.append(artifact)
        return sorted(matches, key=lambda artifact: artifact.path)

    def _extract_metric_records_from_source(self, art: Artifact, source: Any, prefix: str) -> None:
        if "evaluation_result" not in art.roles or not isinstance(source, dict):
            return

        metrics = source.get("metrics")
        if isinstance(metrics, dict):
            for metric_name in sorted(metrics):
                self._append_metric_record(
                    art,
                    metric_name,
                    metrics[metric_name],
                    f"{prefix}.metrics.{metric_name}".lstrip("."),
                )
        elif isinstance(metrics, list):
            for index, metric in enumerate(metrics):
                if isinstance(metric, dict):
                    metric_name = metric.get("metric_name", metric.get("metric", metric.get("name")))
                    self._append_metric_record(art, metric_name, metric, f"{prefix}.metrics[{index}]".lstrip("."))

        metric_name = source.get("metric_name", source.get("metric"))
        if metric_name is not None:
            self._append_metric_record(art, metric_name, source, prefix or "root")

    def _append_metric_record(self, art: Artifact, metric_name: Any, metric_spec: Any, field_path: str) -> None:
        if not isinstance(metric_name, str):
            return
        normalized_name = metric_name.strip().lower()
        if normalized_name not in KNOWN_METRIC_NAMES:
            return

        if isinstance(metric_spec, dict):
            value = metric_spec.get("value", metric_spec.get("metric_value"))
            unit = metric_spec.get("unit", metric_spec.get("metric_unit"))
            raw_bounds = metric_spec.get("bounds", metric_spec.get("metric_bounds"))
        else:
            value = metric_spec
            unit = None
            raw_bounds = None

        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return

        bounds: Optional[List[float]] = None
        if isinstance(raw_bounds, (list, tuple)) and len(raw_bounds) == 2:
            if all(
                isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item))
                for item in raw_bounds
            ):
                lower, upper = float(raw_bounds[0]), float(raw_bounds[1])
                if lower <= upper:
                    bounds = [lower, upper]

        normalized_unit = str(unit).strip().lower() if isinstance(unit, str) else None
        if bounds is None and normalized_unit in {"fraction", "percent", "nonnegative"}:
            bounds = {
                "fraction": [0.0, 1.0],
                "percent": [0.0, 100.0],
                "nonnegative": [0.0, math.inf],
            }[normalized_unit]

        if bounds is None:
            return

        self.metric_records.append(
            MetricRecord(
                artifact_path=art.path,
                metric_name=normalized_name,
                value=float(value),
                unit=normalized_unit,
                bounds=bounds,
                field_path=field_path,
            )
        )
