import json

import pytest
import yaml

import evalproof.cli as cli
from evalproof.artifact import create_artifact_from_file
from evalproof.config import parse_and_validate_config_dict
from evalproof.project_index import ProjectIndex

RULE = "reproducibility.nondeterministic_generation_without_seed"


def scan(root, data, role="evaluation_result", suffix="json", fail_on="high"):
    path = "result." + suffix
    config = {"artifacts": [{"path": path, "roles": [role]}], "similarity": {"enabled": False}}
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    text = yaml.safe_dump(data) if suffix == "yaml" else json.dumps(data)
    if suffix == "toml":
        text = "[generation_params]\ntemperature = 0.7\n"
    (root / path).write_text(text, encoding="utf-8")
    output = root.parent / (root.name + "-report.json")
    code = cli.main(["scan", str(root), "--rules", RULE, "--json", "--output", str(output), "--fail-on", fail_on])
    assert code in {0, 1}
    return code, json.loads(output.read_text(encoding="utf-8"))


@pytest.mark.parametrize("source", ["", "metadata", "eval", "evaluation", "run"])
@pytest.mark.parametrize("alias", ["generation_parameters", "generation_params", "parameters", "params"])
def test_parameter_aliases_and_exact_locations(tmp_path, source, alias):
    data = {alias: {"temperature": 0.7, "api_key": "private-api-value"}}
    if source:
        data = {source: data}
    code, report = scan(tmp_path, data)
    assert code == 0
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    field = (source + "." if source else "") + alias
    assert (finding["severity"], finding["confidence"]) == ("medium", "likely")
    assert finding["locations"][0]["field"] == field + ".temperature"
    assert finding["evidence"] == {
        "result_artifact": "result.json", "parameters_field": field,
        "temperature_field": field + ".temperature", "observed_temperature": 0.7,
        "seed_field": field + ".seed", "seed_state": "missing",
    }
    assert "private-api-value" not in json.dumps(report)


@pytest.mark.parametrize("seed,state", [(None, "null"), (" \t", "blank")])
def test_absent_seed_states_and_opt_in_ci(tmp_path, seed, state):
    code, report = scan(tmp_path, {"params": {"temperature": 1, "seed": seed}}, fail_on="medium")
    assert code == 1
    assert report["findings"][0]["evidence"]["seed_state"] == state


@pytest.mark.parametrize("seed", [0, 42, "recorded-seed", False, [], {}])
def test_present_seed_suppresses_without_validating_provider_types(tmp_path, seed):
    assert scan(tmp_path, {"params": {"temperature": 1, "seed": seed}})[1]["findings"] == []


@pytest.mark.parametrize("temperature", [None, True, False, "0.7", 0, -1, float("inf"), float("nan"), {}, []])
def test_unknown_or_nonpositive_temperature_abstains(tmp_path, temperature):
    assert scan(tmp_path, {"params": {"temperature": temperature}})[1]["findings"] == []


@pytest.mark.parametrize("data", [{}, {"params": []}, [{"params": {"temperature": 1}}], {"metadata": {"nested": {"params": {"temperature": 1}}}}])
def test_unsupported_shapes_abstain(tmp_path, data):
    assert scan(tmp_path, data)[1]["findings"] == []


def test_first_nonnull_alias_wins_without_merging(tmp_path):
    data = {"generation_parameters": "invalid", "params": {"temperature": 1}, "run": {"params": {"temperature": 1}}}
    assert scan(tmp_path, data)[1]["findings"] == []
    data["generation_parameters"] = None
    assert len(scan(tmp_path, data)[1]["findings"]) == 1


def test_sibling_seed_is_not_assumed_to_control_generation(tmp_path):
    assert len(scan(tmp_path, {"seed": 42, "params": {"temperature": 1}})[1]["findings"]) == 1


@pytest.mark.parametrize("role", ["training_dataset", "evaluation_dataset", "rag_document"])
def test_non_result_roles_abstain(tmp_path, role):
    assert scan(tmp_path, {"params": {"temperature": 1}}, role=role)[1]["findings"] == []


@pytest.mark.parametrize("suffix", ["yaml", "toml"])
def test_structured_metadata_formats(tmp_path, suffix):
    assert len(scan(tmp_path, {"generation_params": {"temperature": 0.7}}, suffix=suffix)[1]["findings"]) == 1


def test_repeated_scans_preserve_report_and_fingerprints(tmp_path, monkeypatch):
    data = {"run": {"params": {"temperature": 1}}}
    first = scan(tmp_path, data)[1]
    original = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: list(reversed(original(*a, **kw))))
    second = scan(tmp_path, data)[1]
    for report in [first, second]:
        report["scan"].pop("started_at")
        report["scan"].pop("completed_at")
    assert first == second


def test_index_metadata_locations_reset_on_rebuild(tmp_path):
    (tmp_path / "result.json").write_text('{"run":{"params":{"temperature":1}}}', encoding="utf-8")
    config = parse_and_validate_config_dict({"artifacts": [{"path": "result.json", "roles": ["evaluation_result"]}], "similarity": {"enabled": False}})
    index = ProjectIndex(config)
    index.build([create_artifact_from_file(str(tmp_path), "result.json", config)])
    assert index.eval_metadata_locations["result.json"]["generation_parameters"] == "run.params"
    index.build([])
    assert index.eval_metadata_locations == {}


def test_parse_failure_does_not_invent_generation_metadata(tmp_path):
    (tmp_path / "result.json").write_text('{"params":{"temperature":1}', encoding="utf-8")
    config = parse_and_validate_config_dict({"artifacts": [{"path": "result.json", "roles": ["evaluation_result"]}]})
    index = ProjectIndex(config)
    index.build([create_artifact_from_file(str(tmp_path), "result.json", config)])
    assert index.diagnostics
    assert index.eval_metadata == {}
    assert index.eval_metadata_locations == {}
