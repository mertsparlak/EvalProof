"""CLI entry point and command handler for evalproof."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import List, Optional

from llm_doctor.artifact import create_artifact_from_file
from llm_doctor.config import load_config, ConfigError, ALLOWED_SEVERITIES
from llm_doctor.discovery import discover_files
from llm_doctor.finding import Diagnostic, DiagnosticSeverity, DiagnosticCode, SEVERITY_RANK
from llm_doctor.project_index import ProjectIndex
from llm_doctor.reporting import (
    generate_json_report,
    render_terminal_summary,
    sort_findings_deterministically,
)
from llm_doctor.rule_engine import ScanContext, execute_rules


def run_scan(args: argparse.Namespace) -> int:
    started_at = datetime.now(timezone.utc).isoformat()

    scan_root_input = args.path if args.path else "."
    scan_root_path = Path(scan_root_input).resolve()

    if not scan_root_path.exists() or not scan_root_path.is_dir():
        print(f"Error: Scan root directory not found or unreadable: '{scan_root_input}'", file=sys.stderr)
        return 4

    scan_root = str(scan_root_path)

    # 1. Load configuration
    try:
        cfg = load_config(scan_root, explicit_config_path=args.config)
    except ConfigError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        return 3
    except Exception as err:
        print(f"Failed to load configuration: {err}", file=sys.stderr)
        return 3

    # Override fail_on if specified on CLI
    fail_on = args.fail_on if args.fail_on else cfg.fail_on
    if fail_on.lower() not in ALLOWED_SEVERITIES:
        print(f"Invalid CLI usage: invalid --fail-on value '{fail_on}'", file=sys.stderr)
        return 2

    # 2. Discover candidate files
    try:
        candidate_paths = discover_files(scan_root, cfg)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 4
    except Exception as err:
        print(f"Error discovering files: {err}", file=sys.stderr)
        return 4

    # 3. Detect artifacts and roles
    artifacts_map = {}
    collected_diagnostics: List[Diagnostic] = []

    for rel_path in candidate_paths:
        art = create_artifact_from_file(scan_root, rel_path, cfg)
        if art is not None:
            artifacts_map[art.path] = art
            collected_diagnostics.extend(art.diagnostics)

    # 4. Build project index
    try:
        project_idx = ProjectIndex(cfg)
        project_idx.build(list(artifacts_map.values()))
        collected_diagnostics.extend(project_idx.diagnostics)
    except Exception as err:
        print(f"Unexpected internal error building project index: {err}", file=sys.stderr)
        return 6

    # 5. Execute rules
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

    # Sort findings
    sorted_findings = sort_findings_deterministically(findings)

    # 6. Render report & handle output
    json_report_dict = generate_json_report(
        scan_root=".",
        config_path=cfg.config_path,
        artifacts_scanned=len(artifacts_map),
        findings=sorted_findings,
        diagnostics=diagnostics,
        started_at=started_at,
        completed_at=completed_at,
    )

    if args.output:
        try:
            output_file_path = Path(args.output)
            if not output_file_path.is_absolute():
                output_file_path = Path.cwd() / output_file_path
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(json_report_dict, f, indent=2, ensure_ascii=False)
        except Exception as err:
            print(f"Error writing output to '{args.output}': {err}", file=sys.stderr)
            return 5

    if args.json:
        if not args.output:
            print(json.dumps(json_report_dict, indent=2, ensure_ascii=False))
        else:
            # When --output is used with --json, terminal output should remain concise
            print(f"Scan complete. JSON report written to {args.output}")
    else:
        summary_text = render_terminal_summary(
            scan_root=scan_root,
            artifacts_scanned=len(artifacts_map),
            findings=sorted_findings,
            output_json_path=args.output,
            no_color=args.no_color,
        )
        print(summary_text)

    # 7. Calculate exit code based on fail_on threshold
    fail_on_rank = SEVERITY_RANK.get(fail_on.lower(), 3)
    for f in sorted_findings:
        f_rank = SEVERITY_RANK.get(f.severity.lower(), 0)
        if f_rank >= fail_on_rank:
            return 1

    return 0


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

    scan_parser.add_argument("path", nargs="?", default=".", help="Scan root directory (default: current working directory)")
    scan_parser.add_argument("--config", type=str, help="Use an explicit configuration file.")
    scan_parser.add_argument("--json", action="store_true", help="Write JSON report to stdout.")
    scan_parser.add_argument("--output", type=str, help="Write JSON report to a file. Requires --json.")
    scan_parser.add_argument("--fail-on", type=str, help="Override configured failing severity.")
    scan_parser.add_argument("--no-color", action="store_true", help="Disable terminal colors.")

    # Parse arguments
    try:
        parsed_args = parser.parse_args(sys_args)
    except SystemExit as e:
        # Exit code 2 for invalid CLI usage
        return 2

    if parsed_args.command != "scan":
        print("Invalid command. Available command: scan", file=sys.stderr)
        return 2

    # Validate --output requires --json
    if parsed_args.output and not parsed_args.json:
        print("Invalid CLI usage: --output requires --json.", file=sys.stderr)
        return 2

    # Validate --fail-on if provided
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
