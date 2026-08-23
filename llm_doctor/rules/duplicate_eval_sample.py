"""Rule: contamination.duplicate_eval_sample"""

from typing import Dict, List, Tuple

from llm_doctor.finding import Finding, Location, Severity, Confidence
from llm_doctor.rule_engine import Rule, ScanContext


class DuplicateEvalSampleRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.duplicate_eval_sample"

    @property
    def title(self) -> str:
        return "Duplicate evaluation sample detected"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects duplicate normalized records within evaluation or benchmark datasets."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "duplicate_sample"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        eval_arts = ctx.project_index.artifacts_by_role.get("evaluation_dataset", []) + \
                    ctx.project_index.artifacts_by_role.get("benchmark_dataset", [])

        if not eval_arts:
            return findings

        eval_paths = {a.path for a in eval_arts}

        # Check records grouped by artifact_path and r_hash
        path_hash_rows: Dict[Tuple[str, str], List[int]] = {}
        for r_hash, locations in ctx.project_index.record_hashes.items():
            for path, row in locations:
                if path in eval_paths:
                    path_hash_rows.setdefault((path, r_hash), []).append(row)

        for (path, r_hash), rows in path_hash_rows.items():
            if len(rows) > 1:
                sorted_rows = sorted(rows)
                locs = [Location(role="primary", path=path, row=r) for r in sorted_rows]
                finding = Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=f"Duplicate normalized record found {len(rows)} times in '{path}' at rows {sorted_rows}.",
                    impact="Duplicated samples can overweight repeated cases and distort metrics.",
                    recommendation="Deduplicate the evaluation artifact or justify intentional weighting outside the MVP scanner.",
                    locations=locs,
                    evidence={
                        "artifact_path": path,
                        "duplicate_row_locations": sorted_rows,
                        "normalized_record_hash": r_hash,
                        "duplicate_count": len(rows),
                    },
                )
                findings.append(finding)

        return findings
