"""Reporting pipeline: finding sorting, terminal summary rendering, and JSON report generation."""

import json
from typing import Any, Dict, List, Optional

from evalproof.finding import Diagnostic, Finding, SEVERITY_RANK, Severity


def sort_findings_deterministically(findings: List[Finding]) -> List[Finding]:
    """Sort findings by severity, rule id, primary path, primary location, and fingerprint."""
    def get_sort_key(f: Finding):
        sev_rank = -SEVERITY_RANK.get(f.severity.lower(), 0)
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
    """Sort diagnostics by path, line/row, and code."""
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
    rule_mode: str = "all",
    active_rule_ids: Optional[List[str]] = None,
    artifact_coverage: Optional[List[Dict[str, Any]]] = None,
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

    return {
        "schema_version": "1.0",
        "tool": {
            "name": "evalproof",
            "version": "0.0.0",
        },
        "scan": {
            "root": scan_root,
            "started_at": started_at,
            "completed_at": completed_at,
            "config_path": config_path,
            "rules": {
                "mode": rule_mode,
                "ids": sorted(active_rule_ids or []),
            },
            "artifacts": artifact_coverage or [],
        },
        "summary": {
            "artifacts_scanned": artifacts_scanned,
            "findings_total": len(sorted_findings),
            "findings_by_severity": counts,
        },
        "findings": [f.to_dict() for f in sorted_findings],
        "diagnostics": [d.to_dict() for d in sorted_diagnostics],
    }


def _finding_primary_path(finding: Finding) -> str:
    for loc in finding.locations:
        if loc.path:
            return loc.path
    return "-"


def render_terminal_summary(
    scan_root: str,
    artifacts_scanned: int,
    findings: List[Finding],
    diagnostics: Optional[List[Diagnostic]] = None,
    output_json_path: Optional[str] = None,
    fail_on: str = Severity.HIGH.value,
    ci_failed: bool = False,
    no_color: bool = False,
    rule_mode: str = "all",
    active_rule_ids: Optional[List[str]] = None,
    artifact_coverage: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render human-readable terminal summary for local and CI usage."""
    sorted_findings = sort_findings_deterministically(findings)
    sorted_diagnostics = sort_diagnostics_deterministically(diagnostics or [])
    counts = {
        Severity.CRITICAL.value: 0,
        Severity.HIGH.value: 0,
        Severity.MEDIUM.value: 0,
        Severity.LOW.value: 0,
    }
    for f in sorted_findings:
        if f.severity.lower() in counts:
            counts[f.severity.lower()] += 1

    lines = [
        "=== EvalProof Trust Preflight ===",
        f"Scan root: {scan_root}",
        f"Artifacts scanned: {artifacts_scanned}",
        f"Rules: {rule_mode} ({len(active_rule_ids or [])} active)",
        f"Findings: {len(sorted_findings)} total | critical={counts['critical']} high={counts['high']} medium={counts['medium']} low={counts['low']}",
        f"Diagnostics: {len(sorted_diagnostics)}",
    ]

    coverage = artifact_coverage or []
    indexed = sum(item.get("index_status") == "indexed" for item in coverage)
    partial = sum(item.get("index_status") == "partial" for item in coverage)
    skipped = sum(item.get("index_status") == "skipped" for item in coverage)
    role_conflicts = sum(
        "artifact.role_conflict" in item.get("diagnostic_codes", [])
        for item in coverage
    )
    lines.append(
        f"Coverage: indexed={indexed} partial={partial} skipped={skipped} role_conflicts={role_conflicts}"
    )

    if output_json_path:
        lines.append(f"JSON report: {output_json_path}")

    if ci_failed:
        lines.append(f"CI result: fail (finding at or above {fail_on})")
    else:
        lines.append("CI result: pass")

    if sorted_findings:
        lines.append("")
        lines.append("Top findings:")
        for f in sorted_findings[:5]:
            primary_path = _finding_primary_path(f)
            lines.append(
                f"  - {f.severity.lower()} {f.confidence.lower()} {f.rule_id} ({primary_path}): {f.message}"
            )

    if sorted_diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for d in sorted_diagnostics[:5]:
            path = d.path or "-"
            lines.append(f"  - {d.severity.lower()} {d.code} ({path}): {d.message}")
        if len(sorted_diagnostics) > 5:
            lines.append(f"  - ... {len(sorted_diagnostics) - 5} more diagnostics in JSON report")

    return "\n".join(lines)
