"""Run with an installed wheel's Python, from a directory outside the checkout."""

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

import evalproof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    assert not Path(evalproof.__file__).resolve().is_relative_to(repo)
    assert not Path.cwd().resolve().is_relative_to(repo)
    expected = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert evalproof.__version__ == importlib.metadata.version("evalproof") == expected
    executable = Path(sys.executable).with_name("evalproof.exe" if os.name == "nt" else "evalproof")
    def run(arguments, status):
        result = subprocess.run([str(executable), *map(str, arguments)], capture_output=True, text=True)
        assert result.returncode == status, result.stderr + result.stdout
        return result.stdout
    run(["--help"], 0)
    listing = run(["rules"], 0)
    ids = [line.split(" | ")[0][2:] for line in listing.splitlines() if line.startswith("- ")]
    assert len(ids) == 29 and ids == sorted(set(ids))
    run(["rules", "--unknown"], 2)
    with tempfile.TemporaryDirectory(prefix="evalproof-wheel-smoke-") as directory:
        root = Path(directory)
        for fixture, status in [("accuracy_audit/clean_project", 0), ("contaminated_project", 1)]:
            report_path = root / f"{status}.json"
            run(["scan", repo / "tests" / "fixtures" / fixture, "--json", "--output", report_path], status)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            assert report["tool"]["version"] == expected
            assert report["schema_version"] == "1.0"
        project = root / "dataset"
        project.mkdir()
        output = root / "parquet-report.json"
        if args.parquet:
            import pyarrow as pa
            import pyarrow.parquet as pq
            table = pa.Table.from_pylist([{"id": "private-id", "prompt": "private prompt"}])
            pq.write_table(table, project / "train.parquet")
            pq.write_table(table, project / "eval.parquet")
            run(["scan", project, "--rules", "contamination.train_eval_overlap", "--json", "--output", output], 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            assert len(report["findings"]) == 1
            assert report["diagnostics"] == []
            assert "private" not in json.dumps(report)
        else:
            assert importlib.util.find_spec("pyarrow") is None
            (project / "eval.parquet").write_bytes(b"reader intentionally unavailable")
            run(["scan", project, "--json", "--output", output], 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            assert report["findings"] == []
            assert [d["code"] for d in report["diagnostics"]] == ["artifact.optional_dependency_missing"]
    print(f"Installed {expected} {'parquet' if args.parquet else 'base'} smoke passed outside checkout")


if __name__ == "__main__":
    main()
