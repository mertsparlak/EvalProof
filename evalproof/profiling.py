"""Observed dataset measurements, without rule execution or quality judgments."""

from collections import Counter
import hashlib
import math

from evalproof.config import ArtifactProfileSettings
from evalproof.finding import canonical_json_dumps
from evalproof.measurement import Measurement
from evalproof.project_index import (
    ANSWER_FIELD_ALIASES, INPUT_FIELD_ALIASES, SAMPLE_ID_FIELD_ALIASES,
    ProjectIndex, extract_scalar_field,
)

EXAMPLE_LIMIT = 20


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _lengths(rows, fields, selection):
    lengths = []
    row_numbers = []
    blank_count = 0
    for row in rows:
        if not isinstance(row.row_data, dict):
            continue
        text = next((row.row_data.get(field) for field in fields
                     if isinstance(row.row_data.get(field), str)), None)
        if text is not None:
            lengths.append(len(text))
            row_numbers.append(row.row_num)
            blank_count += not text.strip()
    ordered = sorted(lengths)
    count = len(ordered)
    value = None if not count else {
        "min": ordered[0], "max": ordered[-1],
        "p50": ordered[(50 * count + 99) // 100 - 1],
        "p95": ordered[(95 * count + 99) // 100 - 1],
    }
    return value, count, {
        "string_count": count, "blank_count": blank_count, "excluded_count": len(rows) - count,
        "sample_rows": row_numbers[:EXAMPLE_LIMIT], "evidence_truncated": count > EXAMPLE_LIMIT,
    }, {"fields": list(fields), "selection": selection, "normalization": "none", "percentile": "nearest_rank"}


def _categories(rows, setting):
    counts = Counter()
    values = {}
    missing = null = unsupported = 0
    for row in rows:
        if not isinstance(row.row_data, dict) or setting.name not in row.row_data:
            missing += 1
            continue
        value = row.row_data[setting.name]
        if value is None:
            null += 1
            continue
        if not isinstance(value, (str, bool, int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            unsupported += 1
            continue
        identity = "sha256:" + hashlib.sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()
        counts[identity] += 1
        if setting.expose_values:
            values[identity] = value
    population = sum(counts.values())
    ordered = sorted(counts, key=lambda key: (-counts[key], key))[:EXAMPLE_LIMIT]
    categories = []
    for identity in ordered:
        category = {"category_hash": identity, "count": counts[identity], "fraction": counts[identity] / population}
        if setting.expose_values:
            category["value"] = values[identity]
        categories.append(category)
    return {"categories": categories, "other_count": population - sum(counts[key] for key in ordered)}, population, {
        "accepted_count": population, "missing_count": missing, "null_count": null,
        "unsupported_count": unsupported, "distinct_count": len(counts),
        "reported_category_count": len(ordered), "evidence_truncated": len(counts) > EXAMPLE_LIMIT,
    }


def collect_measurements(index: ProjectIndex) -> list[Measurement]:
    measurements = []
    coverage_by_path = {item["path"]: item for item in index.get_artifact_coverage([])}
    settings_by_path = {item.path: item.profile for item in index.config.artifacts if item.profile is not None}
    for path, artifact in sorted(index.artifacts_by_path.items()):
        if "configuration" in artifact.roles or not artifact.roles.intersection({"training_dataset", "evaluation_dataset", "benchmark_dataset"}):
            continue
        rows = sorted(index.rows_by_artifact.get(path, []), key=lambda row: row.row_num)
        n = len(rows)
        facts = coverage_by_path[path]
        artifact_coverage = {"status": {"indexed": "complete", "partial": "partial", "skipped": "unavailable"}[facts["index_status"]],
                             "reasons": sorted(set(facts["index_reasons"]))}
        row_coverage = {"status": artifact_coverage["status"], "reasons": list(artifact_coverage["reasons"])}
        if path not in index.rows_by_artifact:
            row_coverage = {"status": "unavailable", "reasons": sorted((set(row_coverage["reasons"]) - {"complete"}) | {"no_row_collection"})}

        def emit(name, value, unit, population, method, evidence, parameters=None, scope=None, coverage=None):
            selected_coverage = coverage if coverage is not None else row_coverage
            measurements.append(Measurement(
                measurement_id="dataset." + name, artifact_id=artifact.id, artifact_path=path,
                scope=scope or {"type": "artifact"}, value=value if selected_coverage["status"] != "unavailable" else None,
                unit=unit, population_count=population, coverage=selected_coverage,
                parameters=parameters or {}, method=method, evidence={"rows_indexed": n, **evidence},
            ))

        rejected = facts["rows_rejected"]
        emit("row_count", n, "rows", n, "indexed_rows/v1", {"rows_rejected": rejected, "truncated": facts["truncated"]})
        emit("rejected_record_rate", _ratio(rejected, n + rejected), "fraction", n + rejected,
             "observed_rejections/v1", {"accepted_count": n, "rejected_count": rejected, "observed_count": n + rejected})
        counts = Counter(row.row_hash for row in rows)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        extra = sum(count - 1 for count in counts.values())
        emit("exact_duplicate_rate", _ratio(extra, n), "fraction", n, "normalized_row_duplicates/v1", {
            "duplicate_extra_count": extra, "distinct_record_count": len(counts), "duplicate_group_count": len(duplicates),
            "sample_groups": [{"row_hash": key, "count": counts[key]} for key in duplicates[:EXAMPLE_LIMIT]],
            "evidence_truncated": len(duplicates) > EXAMPLE_LIMIT,
        }, {"normalization": "normalized_row_hash"})
        missing_rows = []
        id_fields = Counter()
        for row in rows:
            selected = extract_scalar_field(row.row_data, SAMPLE_ID_FIELD_ALIASES)
            if selected is None:
                missing_rows.append(row.row_num)
            else:
                id_fields[selected[0]] += 1
        identified = n - len(missing_rows)
        emit("sample_id_coverage", _ratio(identified, n), "fraction", n, "explicit_sample_ids/v1", {
            "identified_count": identified, "missing_count": len(missing_rows),
            "selected_field_counts": dict(sorted(id_fields.items())), "sample_missing_rows": missing_rows[:EXAMPLE_LIMIT],
            "evidence_truncated": len(missing_rows) > EXAMPLE_LIMIT,
        }, {"aliases": list(SAMPLE_ID_FIELD_ALIASES)})
        fields = sorted(set(INPUT_FIELD_ALIASES + ANSWER_FIELD_ALIASES))
        field_counts = {}
        for field in fields:
            present = [row.row_data[field] for row in rows if isinstance(row.row_data, dict) and field in row.row_data]
            field_counts[field] = {"present_count": len(present), "null_count": sum(value is None for value in present),
                                   "blank_string_count": sum(isinstance(value, str) and not value.strip() for value in present)}
        emit("canonical_field_coverage", {field: _ratio(count["present_count"], n) for field, count in field_counts.items()},
             "fraction", n, "top_level_field_presence/v1", {"fields": field_counts}, {"fields": fields})
        settings = settings_by_path.get(path, ArtifactProfileSettings())
        selectors = [(None, INPUT_FIELD_ALIASES)] if settings.text_fields is None else [(field, [field]) for field in settings.text_fields]
        for field, aliases in selectors:
            value, population, evidence, parameters = _lengths(rows, aliases, "field" if field else "first_string")
            emit("input_character_lengths", value, "characters", population, "input_character_lengths/v1", evidence, parameters,
                 {"type": "field", "field": field} if field else None)
        basis = "accepted_rows" if artifact.format in {"jsonl", "csv", "parquet"} else "parsed_object" if artifact.format in {"json", "yaml", "toml"} else "normalized_text"
        emit("artifact_fingerprint", index.artifact_fingerprints.get(path), "sha256", n, "project_index_fingerprint/v1",
             {"fingerprint_basis": basis}, {"normalization": "project_index"}, coverage=artifact_coverage)
        for field in settings.categorical_fields:
            value, population, evidence = _categories(rows, field)
            emit("categorical_distribution", value, "distribution", population, "typed_scalar_distribution/v1", evidence,
                 {"field": field.name, "expose_values": field.expose_values, "normalization": "none",
                  "category_limit": EXAMPLE_LIMIT, "ordering": "count_desc_hash_asc"}, {"type": "field", "field": field.name})
    return measurements
