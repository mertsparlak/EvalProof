"""Rule: contamination.duplicate_train_sample"""

from typing import Dict, List, Tuple

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.rule_engine import Rule, ScanContext


class DuplicateTrainSampleRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.duplicate_train_sample"

    @property
    def title(self) -> str:
        return "Duplicate training sample detected"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects duplicate normalized records within training datasets."

    @property
    def artifact_roles(self) -> List[str]:
        return ["training_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["dataset_integrity", "duplicate_sample", "redundancy"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        train_arts = ctx.project_index.artifacts_by_role.get("training_dataset", [])

        if not train_arts:
            return findings

        train_paths = {a.path for a in train_arts}

        # Check records grouped by artifact_path and r_hash
        path_hash_rows: Dict[Tuple[str, str], List[int]] = {}
        for r_hash, locations in ctx.project_index.record_hashes.items():
            for path, row in locations:
                if path in train_paths:
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
                    message=f"Duplicate normalized training record found {len(rows)} times in '{path}' at rows {sorted_rows[:10]}.",
                    impact="Duplicated training samples cause model overfitting and waste GPU training compute resources.",
                    recommendation="Deduplicate training dataset records to improve model generalization and efficiency.",
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
