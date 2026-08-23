"""Reporting pipeline: finding sorting, terminal summary rendering, and JSON report generation."""

from datetime import datetime, timezone
import json
from typing import Dict, List, Optional, Any

from llm_doctor.finding import Finding, Diagnostic, SEVERITY_RANK, Severity


def sort_findings_deterministically(findings: List[Finding]) -> List[Finding]:
    """Sort findings by:
    1. severity rank (critical > high > medium > low)
    2. rule_id
    3. primary artifact path
    4. primary location line/row
    5. fingerprint
    """
    def get_sort_key(f: Finding):
        sev_rank = -SEVERITY_RANK.get(f.severity.lower(), 0)  # negative so higher rank comes first
        rule_id = f.rule_id

        primary_path = ""
        primary_line_row = 0
        for loc in f.locations:
            if loc.role in {"primary", "source"}:
                primary_path = loc.path or ""
                primary_line_row = loc.line or loc.row or 0
                break
        if not primary_path and f.locations:
            primary_path = f.locations[0].path or ""
            primary_line_row = f.locations[0].line or f.locations[0].row or 0

        return (sev_rank, rule_id, primary_path, primary_line_row, f.fingerprint)

    return sorted(findings, key=get_sort_key)


def sort_diagnostics_deterministically(diagnostics: List[Diagnostic]) -> List[Diagnostic]:
    """Sort diagnostics by path, line/row, code."""
    def get_sort_key(d: Diagnostic):
        path = d.path or ""
        line_row = d.line or d.row or 0
        return (path, line_row, d.code)

    return sorted(diagnostics, key=get_sort_key)


def generate_json_report(
    scan_root: str,
    config_path: Optional[str],
    artifacts_scanned: int,
    findings: List[Finding],
    diagnostics: List[Diagnostic],
    started_at: str,
    completed_at: str,
) -> Dict[str, Any]:
    """Generate machine-readable JSON report structure matching json-report.md v1.0."""
    sorted_findings = sort_findings_deterministically(findings)
    sorted_diagnostics = sort_diagnostics_deterministically(diagnostics)

    counts = {
        Severity.CRITICAL.value: 0,
        Severity.HIGH.value: 0,
        Severity.MEDIUM.value: 0,
        Severity.LOW.value: 0,
    }
    for f in sorted_findings:
        if f.severity.lower() in counts:
            counts[f.severity.lower()] += 1

    report = {
        "schema_version": "1.0",
        "tool": {
            "name": "llm-doctor",
            "version": "0.0.0",
        },
        "scan": {
            "root": scan_root,
            "started_at": started_at,
            "completed_at": completed_at,
            "config_path": config_path,
        },
        "summary": {
            "artifacts_scanned": artifacts_scanned,
            "findings_total": len(sorted_findings),
            "findings_by_severity": counts,
        },
        "findings": [f.to_dict() for f in sorted_findings],
        "diagnostics": [d.to_dict() for d in sorted_diagnostics],
    }
    return report


def render_terminal_summary(
    scan_root: str,
    artifacts_scanned: int,
    findings: List[Finding],
    output_json_path: Optional[str] = None,
    no_color: bool = False,
) -> str:
    """Render human-readable terminal summary."""
    sorted_findings = sort_findings_deterministically(findings)
    counts = {
        Severity.CRITICAL.value: 0,
        Severity.HIGH.value: 0,
        Severity.MEDIUM.value: 0,
        Severity.LOW.value: 0,
    }
    for f in sorted_findings:
        if f.severity.lower() in counts:
            counts[f.severity.lower()] += 1

    lines = []
    lines.append("=== LLM Doctor Preflight Scan Summary ===")
    lines.append(f"Scan root: {scan_root}")
    lines.append(f"Artifacts scanned: {artifacts_scanned}")
    lines.append("Findings by severity:")
    lines.append(f"  Critical : {counts['critical']}")
    lines.append(f"  High     : {counts['high']}")
    lines.append(f"  Medium   : {counts['medium']}")
    lines.append(f"  Low      : {counts['low']}")
    lines.append(f"Total findings: {len(sorted_findings)}")

    if sorted_findings:
        lines.append("")
        lines.append("Highest severity findings:")
        for f in sorted_findings[:10]:
            primary_path = ""
            for loc in f.locations:
                if loc.path:
                    primary_path = loc.path
                    break
            lines.append(f"  [{f.severity.upper()}] {f.rule_id} ({primary_path}): {f.message}")

    if output_json_path:
        lines.append("")
        lines.append(f"JSON report written to: {output_json_path}")

    return "\n".join(lines)
