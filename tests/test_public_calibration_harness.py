import json

import pytest

import release_public_calibration as calibration
from release_public_calibration import materialize_rows, verify_page


def test_mapping_preserves_context_and_source_fields():
    source = {"text": "Question", "context": "Different context", "label": 1}
    rows = materialize_rows([source], {"text": "prompt"})
    assert rows == [{**source, "prompt": "Question"}]
    assert source == {"text": "Question", "context": "Different context", "label": 1}
    assert "id" not in rows[0]


def test_mapping_refuses_to_overwrite_existing_different_field():
    with pytest.raises(ValueError, match="collision"):
        materialize_rows([{"text": "a", "prompt": "b"}], {"text": "prompt"})


def test_mapping_requires_declared_source_field():
    with pytest.raises(ValueError, match="missing"):
        materialize_rows([{"other": "a"}], {"text": "prompt"})


def test_page_rejects_truncated_or_out_of_order_records():
    page = {"rows": [{"row_idx": 0, "row": {"text": "a"}, "truncated_cells": []}]}
    assert verify_page(page, 0) == [{"text": "a"}]
    page["rows"][0]["truncated_cells"] = ["text"]
    with pytest.raises(ValueError, match="truncated"):
        verify_page(page, 0)
    page["rows"][0]["truncated_cells"] = []
    with pytest.raises(ValueError, match="order"):
        verify_page(page, 1)


def test_native_shape_is_not_silently_flattened():
    source = {"question": "q", "answers": {"text": ["a", "b"]}}
    assert materialize_rows([source], {}) == json.loads(json.dumps([source]))


def test_offline_replay_never_fetches_missing_cache(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline replay attempted network access")
    monkeypatch.setattr(calibration, "urlopen", forbidden)
    with pytest.raises(ValueError, match="Missing cached response"):
        calibration.fetch_page(tmp_path, {"dataset": "example/data"}, False)


def test_cached_response_must_match_recorded_hash(tmp_path, monkeypatch):
    params = {"dataset": "example/data"}
    url = "https://datasets-server.huggingface.co/rows?" + calibration.urlencode(params)
    key = calibration.hashlib.sha256(url.encode()).hexdigest()
    raw = b'{"rows":[]}'
    (tmp_path / (key + ".json")).write_bytes(raw)
    receipt = {"url": url, "response_hash": calibration.digest(raw)}
    (tmp_path / (key + ".receipt.json")).write_text(json.dumps(receipt), encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Cached replay attempted network access")
    monkeypatch.setattr(calibration, "urlopen", forbidden)
    assert calibration.fetch_page(tmp_path, params, False)[0] == {"rows": []}
    (tmp_path / (key + ".json")).write_bytes(b'{"rows":[1]}')
    with pytest.raises(ValueError, match="integrity mismatch"):
        calibration.fetch_page(tmp_path, params, False)
