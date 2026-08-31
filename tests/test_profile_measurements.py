import json

import pytest
import yaml

from evalproof.cli import main
from evalproof.config import ConfigError, parse_and_validate_config_dict


def run(root, rows, settings=None, extra=None, raw=None, name="train.jsonl"):
    text = raw if raw is not None else "\n".join(json.dumps(row) for row in rows)
    (root / name).write_text(text, encoding="utf-8")
    entry = {"path": name, "roles": ["training_dataset"]}
    if settings is not None:
        entry["profile"] = settings
    config = {"artifacts": [entry], "include": [name]}
    config.update(extra or {})
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    output = root.parent / (root.name + "-measurements.json")
    code = main(["profile", str(root), "--json", "--output", str(output)])
    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


def get(report, suffix, field=None):
    items = [m for m in report["measurements"] if m["measurement_id"] == "dataset." + suffix
             and (field is None or m["scope"].get("field") == field)]
    assert len(items) == 1
    return items[0]


def test_exact_default_calculations(tmp_path):
    a = {"id": "private-id", "prompt": " aa ", "answer": "private answer", "label": "private category"}
    rows = [a, a, {"id": None, "question": "bbbbb", "answer": None, "label": "other private category"}, {"input": "", "label": False}]
    report = run(tmp_path, rows)
    assert len(report["measurements"]) == 7
    assert get(report, "row_count")["value"] == 4
    assert get(report, "rejected_record_rate")["value"] == 0
    duplicate = get(report, "exact_duplicate_rate")
    assert duplicate["value"] == 0.25
    assert duplicate["evidence"]["duplicate_extra_count"] == 1
    assert duplicate["evidence"]["distinct_record_count"] == 3
    assert get(report, "sample_id_coverage")["value"] == 0.5
    fields = get(report, "canonical_field_coverage")
    assert fields["value"]["prompt"] == 0.5
    assert fields["value"]["input"] == 0.25
    assert fields["value"]["answer"] == 0.75
    assert fields["evidence"]["fields"]["answer"]["null_count"] == 1
    lengths = get(report, "input_character_lengths")
    assert lengths["value"] == {"min": 0, "max": 5, "p50": 4, "p95": 5}
    assert lengths["population_count"] == 4
    assert lengths["evidence"]["blank_count"] == 1
    assert get(report, "artifact_fingerprint")["value"] == report["profile"]["artifacts"][0]["fingerprint"]
    raw = json.dumps(report)
    for secret in ("private-id", "private answer", "private category", "other private category"):
        assert secret not in raw


def test_empty_collection_rates_are_undefined_not_zero(tmp_path):
    report = run(tmp_path, [])
    assert get(report, "row_count")["value"] == 0
    for name in ("rejected_record_rate", "exact_duplicate_rate", "sample_id_coverage", "input_character_lengths"):
        assert get(report, name)["value"] is None
    assert all(value is None for value in get(report, "canonical_field_coverage")["value"].values())
    assert all(m["coverage"]["status"] == "complete" for m in report["measurements"])


def test_rejected_rate_counts_observed_rows_and_marks_partial(tmp_path):
    report = run(tmp_path, [], raw='{}\n{bad}\n\n{}\n')
    value = get(report, "rejected_record_rate")
    assert value["value"] == 1 / 3
    assert value["population_count"] == 3
    assert value["coverage"]["status"] == "partial"
    assert value["evidence"]["rejected_count"] == 1
    assert get(run(tmp_path, [], raw='{bad}\n{bad}\n'), "rejected_record_rate")["value"] == 1


def test_limit_and_unavailable_are_not_full_dataset_measurements(tmp_path):
    report = run(tmp_path, [{"id": 1}, {"id": 2}], extra={"limits": {"max_rows_per_artifact": 1}})
    assert get(report, "row_count")["value"] == 1
    assert all(m["coverage"]["status"] == "partial" for m in report["measurements"])
    report = run(tmp_path, [], raw='{broken', name="train.json")
    assert all(m["value"] is None for m in report["measurements"])
    assert all(m["coverage"]["status"] == "unavailable" for m in report["measurements"])


def test_scalar_rows_and_nested_messages_are_not_inferred(tmp_path):
    report = run(tmp_path, [1, 1, {"messages": [{"role": "user", "content": "private prompt"}]}])
    assert get(report, "exact_duplicate_rate")["value"] == 1 / 3
    assert get(report, "input_character_lengths")["value"] is None
    assert get(report, "input_character_lengths")["population_count"] == 0
    assert get(report, "input_character_lengths")["evidence"]["excluded_count"] == 3
    assert get(report, "sample_id_coverage")["value"] == 0


def test_length_selection_empty_first_alias_and_explicit_fields(tmp_path):
    rows = [{"prompt": "", "question": "longer", "custom": "\U0001f642"},
            {"prompt": 123, "question": "abc", "custom": ["not text"]}]
    report = run(tmp_path, rows)
    assert get(report, "input_character_lengths")["value"] == {"min": 0, "max": 3, "p50": 0, "p95": 3}
    report = run(tmp_path, rows, {"text_fields": ["custom", "question"]})
    assert get(report, "input_character_lengths", "custom")["value"]["max"] == 1
    assert get(report, "input_character_lengths", "custom")["population_count"] == 1
    assert get(report, "input_character_lengths", "question")["value"]["p50"] == 3
    assert not any(m["measurement_id"].endswith("input_character_lengths") for m in run(tmp_path, rows, {"text_fields": []})["measurements"])


def test_nearest_rank_p95(tmp_path):
    report = run(tmp_path, [{"prompt": "x" * n} for n in range(1, 101)])
    assert get(report, "input_character_lengths")["value"] == {"min": 1, "max": 100, "p50": 50, "p95": 95}


def test_categorical_type_identity_and_explicit_exposure(tmp_path):
    values = [True, 1, 1.0, "1", None, {}, [], float("nan"), "private category", "private category"]
    rows = [{"label": value} for value in values] + [{}]
    settings = {"categorical_fields": [{"name": "label"}]}
    report = run(tmp_path, rows, settings)
    item = get(report, "categorical_distribution", "label")
    assert item["population_count"] == 6
    assert item["evidence"]["distinct_count"] == 5
    assert item["evidence"]["missing_count"] == 1
    assert item["evidence"]["null_count"] == 1
    assert item["evidence"]["unsupported_count"] == 3
    assert "private category" not in json.dumps(report)
    assert all("value" not in category for category in item["value"]["categories"])
    settings["categorical_fields"][0]["expose_values"] = True
    exposed = get(run(tmp_path, rows, settings), "categorical_distribution", "label")
    assert exposed["parameters"]["expose_values"] is True
    assert exposed["value"]["categories"][0]["value"] == "private category"
    assert exposed["value"]["categories"][0]["fraction"] == 2 / 6


def test_high_cardinality_and_evidence_are_bounded(tmp_path):
    rows = [{"label": f"private-label-{n}", "prompt": "q"} for n in range(50)]
    report = run(tmp_path, rows, {"categorical_fields": [{"name": "label"}]})
    item = get(report, "categorical_distribution", "label")
    assert len(item["value"]["categories"]) == 20
    assert item["value"]["other_count"] == 30
    assert item["evidence"]["distinct_count"] == 50
    assert item["evidence"]["evidence_truncated"] is True
    ids = get(report, "sample_id_coverage")
    assert len(ids["evidence"]["sample_missing_rows"]) == 20
    assert ids["evidence"]["evidence_truncated"] is True


@pytest.mark.parametrize("settings", [None, [], {"unknown": 1}, {"text_fields": "prompt"},
    {"text_fields": ["a", "a"]}, {"text_fields": ["messages.0"]},
    {"categorical_fields": ["label"]}, {"categorical_fields": [{"name": "x", "expose_values": "yes"}]},
    {"categorical_fields": [{"name": "x"}, {"name": "x"}]},
])
def test_invalid_profile_settings(settings):
    with pytest.raises(ConfigError):
        parse_and_validate_config_dict({"artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"], "profile": settings}]})


def test_profile_settings_validate_target_and_are_ignored_by_scan(tmp_path):
    config = {"artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"], "profile": {"text_fields": ["custom"]}}]}
    (tmp_path / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    assert main(["profile", str(tmp_path)]) == 3
    (tmp_path / "train.jsonl").write_text('{}\n', encoding="utf-8")
    out = tmp_path.parent / (tmp_path.name + "-scan.json")
    assert main(["scan", str(tmp_path), "--json", "--output", str(out)]) == 0
    assert "measurements" not in json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,raw", [
    ("train.jsonl", '{"id":"a","prompt":"hello"}\n{"id":"b","prompt":"world!"}'),
    ("train.json", '[{"id":"a","prompt":"hello"},{"id":"b","prompt":"world!"}]'),
    ("train.csv", 'id,prompt\na,hello\nb,world!\n'),
    ("train.yaml", '- id: a\n  prompt: hello\n- id: b\n  prompt: world!\n'),
    ("train.toml", '[[rows]]\nid="a"\nprompt="hello"\n[[rows]]\nid="b"\nprompt="world!"\n'),
])
def test_structured_format_measurements(tmp_path, name, raw):
    report = run(tmp_path, [], name=name, raw=raw)
    assert get(report, "row_count")["value"] == 2
    assert get(report, "sample_id_coverage")["value"] == 1
    assert get(report, "input_character_lengths")["value"] == {"min": 5, "max": 6, "p50": 5, "p95": 6}


def test_no_collection_is_not_empty_and_fingerprint_remains_available(tmp_path):
    report = run(tmp_path, [], name="train.json", raw='{"metadata":"private not a row"}')
    assert get(report, "row_count")["value"] is None
    assert get(report, "row_count")["coverage"] == {"status": "unavailable", "reasons": ["no_row_collection"]}
    assert get(report, "artifact_fingerprint")["value"].startswith("sha256:")
    assert "private not a row" not in json.dumps(report)


def test_duplicate_examples_and_empty_categories(tmp_path):
    rows = [row for n in range(40) for row in [{"value": n}] * 2]
    report = run(tmp_path, rows, {"categorical_fields": [{"name": "label"}]})
    duplicated = get(report, "exact_duplicate_rate")
    assert duplicated["value"] == 0.5
    assert len(duplicated["evidence"]["sample_groups"]) == 20
    assert duplicated["evidence"]["evidence_truncated"] is True
    category = get(report, "categorical_distribution", "label")
    assert category["value"] == {"categories": [], "other_count": 0}
    assert category["population_count"] == 0
    assert category["evidence"]["missing_count"] == 80


def test_setting_order_does_not_change_measurements(tmp_path):
    rows = [{"a": "first", "b": "second"}]
    settings = {"text_fields": ["b", "a"], "categorical_fields": [{"name": "b"}, {"name": "a"}]}
    first = run(tmp_path, rows, settings)
    settings["text_fields"].reverse()
    settings["categorical_fields"].reverse()
    second = run(tmp_path, rows, settings)
    assert first["measurements"] == second["measurements"]


@pytest.mark.parametrize("path,roles", [("train.txt", ["training_dataset"]), ("corpus.jsonl", ["rag_document"]), ("train.jsonl", ["training_dataset", "configuration"])])
def test_profile_settings_reject_inapplicable_targets(path, roles):
    with pytest.raises(ConfigError):
        parse_and_validate_config_dict({"artifacts": [{"path": path, "roles": roles, "profile": {}}]})


def test_declared_profile_target_cannot_be_excluded_or_escape_root(tmp_path):
    (tmp_path / "train.jsonl").write_text('{}', encoding="utf-8")
    for path, exclude in [("train.jsonl", ["train.jsonl"]), ("../train.jsonl", [])]:
        config = {"artifacts": [{"path": path, "roles": ["training_dataset"], "profile": {}}], "exclude": exclude}
        (tmp_path / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        assert main(["profile", str(tmp_path)]) == 3
