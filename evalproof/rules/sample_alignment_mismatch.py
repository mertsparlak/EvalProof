"""Rule: evaluation.sample_alignment_mismatch."""

from collections import Counter
from typing import Any, Dict, List

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import SAMPLE_ID_FIELD_ALIASES, extract_scalar_field
from evalproof.rule_engine import Rule, ScanContext


class SampleAlignmentMismatchRule(Rule):
    @property
    def id(self) -> str:
        return "evaluation.sample_alignment_mismatch"

    @property
    def title(self) -> str:
        return "Evaluation result samples do not align with the dataset"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects count or explicit sample-ID mismatches between an evaluation result and its fingerprint-matched dataset."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_result", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["evaluation_integrity", "sample_alignment", "reproducibility"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        result_artifacts = sorted(
            ctx.project_index.artifacts_by_role.get("evaluation_result", []),
            key=lambda artifact: artifact.path,
        )
        dataset_roles = {"evaluation_dataset", "benchmark_dataset"}

        for result_artifact in result_artifacts:
            metadata = ctx.project_index.eval_metadata.get(result_artifact.path, {})
            dataset_fingerprint = metadata.get("dataset_fingerprint")
            if not dataset_fingerprint:
                continue

            matches = ctx.project_index.matching_artifacts_for_fingerprint(dataset_fingerprint, dataset_roles)
            if not matches:
                continue

            dataset_artifact = matches[0]
            dataset_rows = ctx.project_index.rows_by_artifact.get(dataset_artifact.path, [])
            result_rows = ctx.project_index.rows_by_artifact.get(result_artifact.path, [])
            if not dataset_rows or not result_rows:
                continue

            mismatch_types: List[str] = []
            dataset_count = len(dataset_rows)
            result_count = len(result_rows)
            if dataset_count != result_count:
                mismatch_types.append("count_mismatch")

            dataset_ids = self._extract_ids(dataset_rows)
            result_ids = self._extract_ids(result_rows)
            evidence: Dict[str, Any] = {
                "result_artifact": result_artifact.path,
                "dataset_artifact": dataset_artifact.path,
                "matched_dataset_artifact_paths": [artifact.path for artifact in matches],
                "dataset_fingerprint": str(dataset_fingerprint),
                "dataset_count": dataset_count,
                "result_count": result_count,
            }

            if dataset_ids is not None and result_ids is not None:
                dataset_set = set(dataset_ids)
                result_set = set(result_ids)
                missing_ids = sorted(dataset_set - result_set)
                unexpected_ids = sorted(result_set - dataset_set)
                duplicate_dataset_ids = sorted(identifier for identifier, count in Counter(dataset_ids).items() if count > 1)
                duplicate_result_ids = sorted(identifier for identifier, count in Counter(result_ids).items() if count > 1)

                if missing_ids:
                    mismatch_types.append("missing_ids")
                    evidence["missing_ids"] = missing_ids[:20]
                if unexpected_ids:
                    mismatch_types.append("unexpected_ids")
                    evidence["unexpected_ids"] = unexpected_ids[:20]
                if duplicate_dataset_ids or duplicate_result_ids:
                    mismatch_types.append("duplicate_ids")
                    evidence["duplicate_dataset_ids"] = duplicate_dataset_ids[:20]
                    evidence["duplicate_result_ids"] = duplicate_result_ids[:20]

            if not mismatch_types:
                continue

            evidence["mismatch_types"] = mismatch_types
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Evaluation result '{result_artifact.path}' does not align with "
                        f"fingerprint-matched dataset '{dataset_artifact.path}': {', '.join(mismatch_types)}."
                    ),
                    impact="The reported evaluation metrics may be computed over a different or incomplete set of samples.",
                    recommendation="Regenerate the result with the fingerprint-matched dataset and preserve stable sample IDs.",
                    locations=[
                        Location(role="primary", path=result_artifact.path),
                        Location(role="related", path=dataset_artifact.path),
                    ],
                    evidence=evidence,
                )
            )

        return findings

    @staticmethod
    def _extract_ids(rows: list) -> List[str] | None:
        identifiers: List[str] = []
        for row in rows:
            extracted = extract_scalar_field(row.row_data, SAMPLE_ID_FIELD_ALIASES)
            if extracted is None:
                return None
            identifiers.append(extracted[1])
        return identifiers