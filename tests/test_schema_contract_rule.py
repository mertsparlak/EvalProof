from __future__ import annotations

import json
from pathlib import Path

import yaml

from evalproof.cli import main


RULE_ID = "dataset.schema_contract_violation"


def write_config(root: Path, fields: dict, required: tuple[str, ...] = ()) -> None:
    (root / "evalproof.yaml").write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {
                        "path": "train.jsonl",
                        "roles": ["training_dataset"],
                        "schema": {"required": list(required), "fields": fields},
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def scan(root: Path) -> tuple[int, dict]:
    output = root.parent / f"{root.name}-schema-report.json"
    ret = main(
        [
            "scan",
            str(root),
            "--json",
            "--output",
            str(output),
            "--rules",
            RULE_ID,
        ]
    )
    assert output.exists()
    return ret, json.loads(output.read_text(encoding="utf-8"))


def schema_findings(report: dict) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == RULE_ID]


def test_aggregates_object_parse_required_null_and_type_violations(tmp_path):
    write_config(
        tmp_path,
        {"messages": {"type": "array", "nullable": False}},
        required=("messages",),
    )
    (tmp_path / "train.jsonl").write_text(
        '{"sample":"missing-secret-value"}\n'
        '{"messages":null}\n'
        '{"messages":"raw-secret-value"}\n'
        '"not-an-object"\n'
        '{malformed-json}\n'
        '{"messages":[{"role":"user","content":"valid-secret-value"}]}\n',
        encoding="utf-8",
    )

    ret, report = scan(tmp_path)

    assert ret == 1
    findings = schema_findings(report)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["total_violation_count"] == 5
    assert finding["evidence"]["affected_row_count"] == 5
    assert finding["evidence"]["violation_counts"] == {
        "null_not_allowed": 1,
        "record_not_object": 1,
        "record_unparseable": 1,
        "required_field_missing": 1,
        "type_mismatch": 1,
    }
    serialized = json.dumps(finding)
    for raw_value in ["missing-secret-value", "raw-secret-value", "valid-secret-value"]:
        assert raw_value not in serialized


def test_validates_types_without_coercion_and_allows_optional_extra_fields(tmp_path):
    write_config(
        tmp_path,
        {
            "text": {"type": "string"},
            "count": {"type": "integer"},
            "score": {"type": "number"},
            "enabled": {"type": "boolean"},
            "metadata": {"type": "object"},
            "messages": {"type": "array"},
            "optional": {"type": "string", "nullable": True},
        },
        required=("text", "count", "score", "enabled", "metadata", "messages"),
    )
    (tmp_path / "train.jsonl").write_text(
        '{"text":"ok","count":2,"score":1.5,"enabled":true,"metadata":{},"messages":[],"extra":"allowed"}\n'
        '{"text":"ok","count":true,"score":false,"enabled":true,"metadata":{},"messages":[]}\n'
        '{"text":"ok","count":"42","score":2,"enabled":true,"metadata":{},"messages":[],"optional":null}\n',
        encoding="utf-8",
    )

    ret, report = scan(tmp_path)

    assert ret == 1
    finding = schema_findings(report)[0]
    assert finding["evidence"]["violation_counts"] == {"type_mismatch": 3}
    samples = finding["evidence"]["sample_violations"]
    assert [(item["row"], item["field"]) for item in samples] == [
        (2, "count"),
        (2, "score"),
        (3, "count"),
    ]


def test_reports_missing_record_collection_but_accepts_empty_collection(tmp_path):
    fields = {"prompt": {"type": "string"}}
    write_config(tmp_path, fields, required=("prompt",))
    (tmp_path / "train.jsonl").unlink(missing_ok=True)
    (tmp_path / "train.jsonl").write_text('{"metadata":{"source":"not-a-row-list"}}\n', encoding="utf-8")

    ret, report = scan(tmp_path)
    assert ret == 1
    assert schema_findings(report)[0]["evidence"]["violation_counts"] == {
        "required_field_missing": 1
    }

    config = (tmp_path / "evalproof.yaml").read_text(encoding="utf-8").replace(
        "train.jsonl", "train.json"
    )
    (tmp_path / "evalproof.yaml").write_text(config, encoding="utf-8")
    (tmp_path / "train.jsonl").unlink()
    (tmp_path / "train.json").write_text('{"metadata":{"source":"not-a-row-list"}}', encoding="utf-8")

    ret, report = scan(tmp_path)
    assert ret == 1
    assert schema_findings(report)[0]["evidence"]["violation_counts"] == {
        "record_collection_unavailable": 1
    }

    (tmp_path / "train.json").write_text("[]", encoding="utf-8")
    ret, report = scan(tmp_path)
    assert ret == 0
    assert schema_findings(report) == []


def test_bounds_evidence_and_keeps_fingerprint_deterministic(tmp_path):
    write_config(
        tmp_path,
        {"prompt": {"type": "string"}},
        required=("prompt",),
    )
    (tmp_path / "train.jsonl").write_text(
        "".join('{"other":%d}\n' % index for index in range(30)),
        encoding="utf-8",
    )

    reports = []
    for _ in range(2):
        ret, report = scan(tmp_path)
        assert ret == 1
        reports.append(report)

    first = schema_findings(reports[0])[0]
    second = schema_findings(reports[1])[0]
    assert first == second
    assert first["evidence"]["total_violation_count"] == 30
    assert len(first["evidence"]["sample_violations"]) == 20
    assert first["evidence"]["evidence_truncated"] is True
