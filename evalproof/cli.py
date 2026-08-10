"""CLI entry point and command handler for evalproof."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import List, Optional

from evalproof.artifact import create_artifact_from_file
from evalproof.config import ALLOWED_SEVERITIES, DEFAULT_FAIL_ON, ConfigError, load_config
from evalproof.discovery import discover_files
from evalproof.finding import Diagnostic, SEVERITY_RANK
from evalproof.project_index import ProjectIndex
from evalproof.reporting import (
    generate_json_report,
    render_terminal_summary,
    sort_findings_deterministically,
)
from evalproof.rule_engine import ScanContext, default_registry, execute_rules
import evalproof.rules  # Ensures built-in MVP rules are registered


RULE_CONFIDENCE = {
    "contamination.train_eval_overlap": "confirmed",
    "contamination.train_eval_near_duplicate": "likely",
    "contamination.duplicate_eval_sample": "confirmed",
    "contamination.duplicate_eval_near_duplicate": "likely",
    "contamination.duplicate_train_sample": "confirmed",
    "contamination.duplicate_train_near_duplicate": "likely",
    "contamination.rag_answer_leakage": "likely",
    "contamination.missing_repro_metadata": "confirmed",
    "contamination.fingerprint_mismatch": "confirmed",
    "contamination.untrusted_context_interpolation": "heuristic",
    "contamination.sensitive_value_exposure": "heuristic",
}


def rule_fails_default_ci(rule_id: str, severity: str) -> bool:
    confidence = RULE_CONFIDENCE.get(rule_id, "likely")
    if confidence == "heuristic":
        return False
    return SEVERITY_RANK.get(severity.lower(), 0) >= SEVERITY_RANK[DEFAULT_FAIL_ON]


def render_rules_listing() -> str:
    lines = ["EvalProof Built-in Rules", ""]
    for rule in sorted(default_registry.get_all_rules(), key=lambda r: r.id):
        confidence = RULE_CONFIDENCE.get(rule.id, "likely")
        ci_behavior = "fails default CI" if rule_fails_default_ci(rule.id, rule.default_severity) else "does not fail default CI"
        tags = ",".join(rule.tags)
        lines.append(
            f"- {rule.id} | severity={rule.default_severity} | confidence={confidence} | {ci_behavior} | tags={tags} | {rule.title}"
        )
    return "\n".join(lines)


def has_failing_finding(findings, fail_on: str) -> bool:
    fail_on_rank = SEVERITY_RANK.get(fail_on.lower(), 3)
    for finding in findings:
        finding_rank = SEVERITY_RANK.get(finding.severity.lower(), 0)
        if finding_rank >= fail_on_rank:
            return True
    return False


def run_scan(args: argparse.Namespace) -> int:
    started_at = datetime.now(timezone.utc).isoformat()

    scan_root_input = args.path if args.path else "."
    scan_root_path = Path(scan_root_input).resolve()

    if not scan_root_path.exists() or not scan_root_path.is_dir():
        print(f"Error: Scan root directory not found or unreadable: '{scan_root_input}'", file=sys.stderr)
        return 4

    scan_root = str(scan_root_path)

    try:
        cfg = load_config(scan_root, explicit_config_path=args.config)
    except ConfigError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        return 3
    except Exception as err:
        print(f"Failed to load configuration: {err}", file=sys.stderr)
        return 3

    fail_on = args.fail_on if args.fail_on else cfg.fail_on
    if fail_on.lower() not in ALLOWED_SEVERITIES:
        print(f"Invalid CLI usage: invalid --fail-on value '{fail_on}'", file=sys.stderr)
        return 2

    try:
        candidate_paths = discover_files(scan_root, cfg)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 4
    except Exception as err:
        print(f"Error discovering files: {err}", file=sys.stderr)
        return 4

    artifacts_map = {}
    collected_diagnostics: List[Diagnostic] = []

    for rel_path in candidate_paths:
        artifact = create_artifact_from_file(scan_root, rel_path, cfg)
        if artifact is not None:
            artifacts_map[artifact.path] = artifact
            collected_diagnostics.extend(artifact.diagnostics)

    try:
        project_idx = ProjectIndex(cfg)
        project_idx.build(list(artifacts_map.values()))
        collected_diagnostics.extend(project_idx.diagnostics)
    except Exception as err:
        print(f"Unexpected internal error building project index: {err}", file=sys.stderr)
        return 6

    try:
        ctx = ScanContext(
            scan_root=scan_root,
            config=cfg,
            artifacts=artifacts_map,
            project_index=project_idx,
            diagnostics=collected_diagnostics,
        )
        findings, diagnostics = execute_rules(ctx)
    except Exception as err:
        print(f"Unexpected internal error executing rules: {err}", file=sys.stderr)
        return 6

    completed_at = datetime.now(timezone.utc).isoformat()
    sorted_findings = sort_findings_deterministically(findings)
    ci_failed = has_failing_finding(sorted_findings, fail_on)

    json_report_dict = generate_json_report(
        scan_root=".",
        config_path=cfg.config_path,
        artifacts_scanned=len(artifacts_map),
        findings=sorted_findings,
        diagnostics=diagnostics,
        started_at=started_at,
        completed_at=completed_at,
    )

    output_path = args.output
    if not output_path:
        output_path = str(Path(scan_root) / "evalproof_report.json")

    try:
        output_file_path = Path(output_path)
        if not output_file_path.is_absolute():
            output_file_path = Path.cwd() / output_file_path
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(json_report_dict, f, indent=2, ensure_ascii=False)
    except Exception as err:
        print(f"Error writing output to '{output_path}': {err}", file=sys.stderr)
        return 5

    if args.json:
        if not args.output:
            print(json.dumps(json_report_dict, indent=2, ensure_ascii=False))
        else:
            print(f"Scan complete. JSON report written to {args.output}")
    else:
        summary_text = render_terminal_summary(
            scan_root=scan_root,
            artifacts_scanned=len(artifacts_map),
            findings=sorted_findings,
            diagnostics=diagnostics,
            output_json_path=str(output_file_path),
            fail_on=fail_on,
            ci_failed=ci_failed,
            no_color=args.no_color,
        )
        print(summary_text)

    return 1 if ci_failed else 0


def main(sys_args: Optional[List[str]] = None) -> int:
    if sys_args is None:
        sys_args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="evalproof",
        description="EvalProof static preflight scanner for LLM evaluation artifacts",
        add_help=True,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    scan_parser = subparsers.add_parser("scan", help="Scan repository for contamination and trust issues")
    subparsers.add_parser("rules", help="List built-in EvalProof rules")

    scan_parser.add_argument("path", nargs="?", default=".", help="Scan root directory (default: current working directory)")
    scan_parser.add_argument("--config", type=str, help="Use an explicit configuration file.")
    scan_parser.add_argument("--json", action="store_true", help="Write JSON report to stdout.")
    scan_parser.add_argument("--output", type=str, help="Write JSON report to a file. Requires --json.")
    scan_parser.add_argument("--fail-on", type=str, help="Override configured failing severity.")
    scan_parser.add_argument("--no-color", action="store_true", help="Disable terminal colors.")

    try:
        parsed_args = parser.parse_args(sys_args)
    except SystemExit:
        return 2

    if parsed_args.command == "rules":
        print(render_rules_listing())
        return 0

    if parsed_args.command != "scan":
        print("Invalid command. Available commands: scan, rules", file=sys.stderr)
        return 2

    if parsed_args.output and not parsed_args.json:
        print("Invalid CLI usage: --output requires --json.", file=sys.stderr)
        return 2

    if parsed_args.fail_on and parsed_args.fail_on.lower() not in ALLOWED_SEVERITIES:
        print(f"Invalid CLI usage: invalid --fail-on value '{parsed_args.fail_on}'.", file=sys.stderr)
        return 2

    try:
        return run_scan(parsed_args)
    except FileNotFoundError as err:
        print(f"File not found: {err}", file=sys.stderr)
        return 4
    except ConfigError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        return 3
    except Exception as err:
        print(f"Unexpected internal error: {err}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    sys.exit(main())