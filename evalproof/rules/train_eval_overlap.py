"""Rule: contamination.train_eval_overlap"""

from typing import Dict, List, Set, Tuple

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.rule_engine import Rule, ScanContext


class TrainEvalOverlapRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.train_eval_overlap"

    @property
    def title(self) -> str:
        return "Train/eval overlap detected"

    @property
    def default_severity(self) -> str:
        return Severity.CRITICAL.value

    @property
    def description(self) -> str:
        return "Detects exact normalized records that appear in both training datasets and evaluation or benchmark datasets."

    @property
    def artifact_roles(self) -> List[str]:
        return ["training_dataset", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "split_leakage"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        train_arts = ctx.project_index.artifacts_by_role.get("training_dataset", [])
        eval_arts = ctx.project_index.artifacts_by_role.get("evaluation_dataset", []) + \
                    ctx.project_index.artifacts_by_role.get("benchmark_dataset", [])

        if not train_arts or not eval_arts:
            return findings

        train_paths = {a.path for a in train_arts}
        eval_paths = {a.path for a in eval_arts}

        for r_hash, locations in ctx.project_index.record_hashes.items():
            train_locs = [(path, row) for path, row in locations if path in train_paths]
            eval_locs = [(path, row) for path, row in locations if path in eval_paths]

            if train_locs and eval_locs:
                # Group overlap by train_path and eval_path
                for train_path, train_row in train_locs:
                    for eval_path, eval_row in eval_locs:
                        loc_source = Location(role="source", path=train_path, row=train_row)
                        loc_target = Location(role="target", path=eval_path, row=eval_row)

                        finding = Finding(
                            rule_id=self.id,
                            severity=self.default_severity,
                            confidence=Confidence.CONFIRMED.value,
                            title=self.title,
                            message=f"Normalized record in '{train_path}' (row {train_row}) also appears in '{eval_path}' (row {eval_row}).",
                            impact="Evaluation results may be inflated because evaluation samples may have appeared in training data.",
                            recommendation="Remove overlapping records from one split and regenerate dataset fingerprints.",
                            locations=[loc_source, loc_target],
                            evidence={
                                "training_artifact": train_path,
                                "training_row": train_row,
                                "evaluation_artifact": eval_path,
                                "evaluation_row": eval_row,
                                "normalized_record_hash": r_hash,
                                "overlap_count": 1,
                            },
                        )
                        findings.append(finding)

        return findings
