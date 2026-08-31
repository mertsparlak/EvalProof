"""Opt-in release calibration; downloads and reports must stay outside the checkout.

Run with --fetch once; subsequent runs replay cached, hash-verified API responses.
Prefix samples are not representative precision/recall estimates.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evalproof.cli import main as evalproof_main

# Explicit calibration mappings, not product-side schema inference.
CASES = [
    ("deepset/prompt-injections", [("default", "train", "training_dataset", 500, {"text": "prompt"}),
                                  ("default", "test", "evaluation_dataset", 500, {"text": "prompt"})]),
    ("lmsys/toxic-chat", [("toxicchat0124", "train", "training_dataset", 500, {"user_input": "prompt", "conv_id": "id"}),
                         ("toxicchat0124", "test", "evaluation_dataset", 500, {"user_input": "prompt", "conv_id": "id"})]),
    ("xTRam1/safe-guard-prompt-injection", [("default", "train", "training_dataset", 500, {"text": "prompt"}),
                                         ("default", "test", "evaluation_dataset", 500, {"text": "prompt"})]),
    ("nvidia/Aegis-AI-Content-Safety-Dataset-2.0", [("default", "train", "training_dataset", 500, {}),
                                                ("default", "test", "evaluation_dataset", 500, {})]),
    ("openai/gsm8k", [("main", "train", "training_dataset", 500, {}),
                     ("main", "test", "evaluation_dataset", 500, {})]),
    ("rajpurkar/squad", [("plain_text", "train", "training_dataset", 500, {}),
                        ("plain_text", "validation", "evaluation_dataset", 500, {})]),
    ("truthfulqa/truthful_qa", [("generation", "validation", "benchmark_dataset", 1000, {"best_answer": "answer"})]),
    *[(name, [("corpus", "corpus", "rag_document", 500, {"_id": "doc_id"}),
              ("queries", "queries", "evaluation_dataset", 500, {"_id": "id", "text": "question"})])
      for name in ("BeIR/fiqa", "BeIR/nfcorpus", "BeIR/scifact")],
]


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def materialize_rows(rows, mapping):
    result = []
    for source in rows:
        row = dict(source)
        for old, new in mapping.items():
            if old not in source:
                raise ValueError("Declared source field is missing")
            if new in source and source[new] != source[old]:
                raise ValueError("Declared field mapping collision")
            row[new] = source[old]
        result.append(row)
    return result


def verify_page(page, offset):
    result = []
    for expected, item in enumerate(page["rows"], offset):
        if item["row_idx"] != expected:
            raise ValueError("Unexpected row order")
        if item.get("truncated_cells"):
            raise ValueError("Viewer returned truncated cells")
        if not isinstance(item["row"], dict):
            raise ValueError("Viewer record is not an object")
        result.append(item["row"])
    return result


def fetch_page(cache, params, fetch):
    url = "https://datasets-server.huggingface.co/rows?" + urlencode(params)
    key = hashlib.sha256(url.encode()).hexdigest()
    raw_path = cache / (key + ".json")
    receipt_path = cache / (key + ".receipt.json")
    if not raw_path.exists():
        if not fetch:
            raise ValueError("Missing cached response; explicitly use --fetch")
        with urlopen(url, timeout=60) as response:
            raw = response.read()
        time.sleep(2)
        receipt = {"url": url, "response_hash": digest(raw),
                   "retrieved_at": datetime.now(timezone.utc).isoformat()}
        raw_path.write_bytes(raw)
        receipt_path.write_text(encode(receipt), encoding="utf-8")
    raw = raw_path.read_bytes()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["url"] != url or receipt["response_hash"] != digest(raw):
        raise ValueError("Cached response integrity mismatch")
    return json.loads(raw), receipt


def run(output, fetch=False):
    output = output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if output == repo or output.is_relative_to(repo):
        raise ValueError("Public calibration data must remain outside the repository")
    cache = output / "responses"
    cache.mkdir(parents=True, exist_ok=True)
    source_hash = digest("\n".join(
        path.relative_to(repo).as_posix() + ":" + digest(path.read_bytes())
        for path in sorted((repo / "evalproof").rglob("*.py"))
    ).encode())
    records = []
    for number, (dataset, partitions) in enumerate(CASES, 1):
        case_root = output / f"case-{number:02d}"
        project = case_root / "project"
        project.mkdir(parents=True, exist_ok=True)
        config = {"include": [], "artifacts": []}
        sources = []
        for index, (subset, split, role, limit, mapping) in enumerate(partitions):
            rows, receipts = [], []
            total = None
            while len(rows) < limit and (total is None or len(rows) < total):
                params = {"dataset": dataset, "config": subset, "split": split,
                          "offset": len(rows), "length": min(100, limit - len(rows))}
                page, receipt = fetch_page(cache, params, fetch)
                batch = verify_page(page, len(rows))
                total = page["num_rows_total"]
                if not batch:
                    raise ValueError("Viewer returned an empty page before the sample boundary")
                rows.extend(batch)
                receipts.append({**receipt, "offset": params["offset"], "length": params["length"],
                                 "observed_count": len(batch), "total_rows": total,
                                 "viewer_partial": page.get("partial")})
            mapped = materialize_rows(rows, mapping)
            name = f"part-{index}.jsonl"
            raw = ("\n".join(encode(row) for row in mapped) + "\n").encode("utf-8")
            (project / name).write_bytes(raw)
            config["include"].append(name)
            config["artifacts"].append({"path": name, "roles": [role]})
            sources.append({"config": subset, "split": split, "role": role, "path": name,
                            "mapping": mapping, "rows": len(rows), "total_rows": total,
                            "materialized_file_hash": digest(raw), "responses": receipts})
        config_text = yaml.safe_dump(config, sort_keys=True)
        (project / "evalproof.yaml").write_text(config_text, encoding="utf-8")
        started = time.perf_counter()
        reports = {}
        for command in ("scan", "profile"):
            report_path = case_root / (command + ".json")
            # CLI JSON may contain large reports; it is retained at report_path.
            with contextlib.redirect_stdout(io.StringIO()):
                code = evalproof_main([command, str(project), "--json", "--output", str(report_path)])
            if code not in ((0, 1) if command == "scan" else (0,)):
                raise ValueError(f"{command} failed with exit code {code}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if command == "scan" and len(report["scan"]["rules"]["ids"]) != 29:
                raise ValueError("Calibration requires all 29 release rules")
            report[command].pop("started_at")
            report[command].pop("completed_at")
            reports[command] = {"exit_code": code, "summary": report["summary"],
                                "diagnostics": report["diagnostics"],
                                "report_hash": digest(report_path.read_bytes()),
                                "normalized_report_hash": digest(encode(report).encode())}
        records.append({"dataset": dataset, "sources": sources, "reports": reports,
                        "scanner_source_hash": source_hash,
                        "harness_hash": digest(Path(__file__).read_bytes()),
                        "config_hash": digest(config_text.encode()),
                        "seconds": round(time.perf_counter() - started, 3)})
        (output / "manifest.json").write_text(encode(records), encoding="utf-8")
        print(encode({"dataset": dataset, "rows": sum(s["rows"] for s in sources),
                      "scan": reports["scan"]["summary"], "seconds": records[-1]["seconds"]}), flush=True)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    run(args.output, args.fetch)
