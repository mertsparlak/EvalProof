from __future__ import annotations

import pytest
import yaml

from evalproof.cli import main
from evalproof.config import ConfigError, parse_and_validate_config_dict


def schema_artifact(**schema_overrides):
    schema = {
        "required": ["messages"],
        "fields": {
            "messages": {"type": "array", "nullable": False},
            "sample_id": {"type": "string", "nullable": True},
        },
    }
    schema.update(schema_overrides)
    return {
        "path": "data/train.jsonl",
        "roles": ["training_dataset"],
        "schema": schema,
    }


def test_parses_explicit_artifact_schema_contract():
    cfg = parse_and_validate_config_dict({"artifacts": [schema_artifact()]})

    contract = cfg.artifacts[0].schema
    assert contract is not None
    assert contract.required == ["messages"]
    assert contract.fields["messages"].type == "array"
    assert contract.fields["messages"].nullable is False
    assert contract.fields["sample_id"].nullable is True


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (schema_artifact(unknown=True), "Invalid key under artifact schema"),
        (
            schema_artifact(fields={"messages": {"type": "vector"}}),
            "Invalid schema field type",
        ),
        (
            schema_artifact(required=["missing"]),
            "must also be declared under 'fields'",
        ),
        (
            schema_artifact(fields={"nested.value": {"type": "string"}}),
            "top-level field name",
        ),
    ],
)
def test_rejects_invalid_schema_contracts(artifact, message):
    with pytest.raises(ConfigError, match=message):
        parse_and_validate_config_dict({"artifacts": [artifact]})


def test_rejects_duplicate_artifact_paths():
    with pytest.raises(ConfigError, match="Duplicate artifact path"):
        parse_and_validate_config_dict(
            {
                "artifacts": [
                    {"path": "data/train.jsonl", "roles": ["training_dataset"]},
                    {"path": "./data\\train.jsonl", "roles": ["training_dataset"]},
                ]
            }
        )


def test_rejects_schema_for_non_dataset_role_or_unsupported_format():
    artifact = schema_artifact()
    artifact["roles"] = ["evaluation_result"]
    with pytest.raises(ConfigError, match="dataset artifact roles"):
        parse_and_validate_config_dict({"artifacts": [artifact]})

    artifact = schema_artifact()
    artifact["path"] = "data/train.txt"
    with pytest.raises(ConfigError, match="structured dataset format"):
        parse_and_validate_config_dict({"artifacts": [artifact]})


def test_csv_schema_accepts_only_string_fields():
    artifact = schema_artifact(fields={"prompt": {"type": "integer"}})
    artifact["path"] = "data/train.csv"

    with pytest.raises(ConfigError, match="CSV schema fields must use type 'string'"):
        parse_and_validate_config_dict({"artifacts": [artifact]})


@pytest.mark.parametrize("case", ["missing", "excluded", "outside_root"])
def test_scan_rejects_unreachable_schema_artifact_paths(tmp_path, case):
    artifact = schema_artifact()
    artifact["path"] = "data/train.jsonl"
    config = {"artifacts": [artifact]}

    if case == "excluded":
        target = tmp_path / "data" / "train.jsonl"
        target.parent.mkdir()
        target.write_text('{"messages":[]}\n', encoding="utf-8")
        config["exclude"] = ["data/**"]
    elif case == "outside_root":
        artifact["path"] = "../outside.jsonl"

    (tmp_path / "evalproof.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    assert main(["scan", str(tmp_path), "--rules", "dataset.schema_contract_violation"]) == 3
