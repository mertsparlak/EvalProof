"""Rule: evaluation.metric_out_of_bounds."""

import math
from typing import List

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext


class MetricOutOfBoundsRule(Rule):
    @property
    def id(self) -> str:
        return "evaluation.metric_out_of_bounds"

    @property
    def title(self) -> str:
        return "Evaluation metric is outside its declared bounds"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects known evaluation metrics whose numeric values violate an explicit unit or bounds contract."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_result"]

    @property
    def tags(self) -> List[str]:
        return ["evaluation_integrity", "metrics", "reproducibility"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        records = sorted(
            ctx.project_index.metric_records,
            key=lambda record: (record.artifact_path, record.field_path, record.metric_name),
        )

        for record in records:
            lower, upper = record.bounds
            if lower <= record.value <= upper:
                continue

            accepted_bounds = [
                None if math.isinf(bound) else bound
                for bound in record.bounds
            ]
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Metric '{record.metric_name}' in '{record.artifact_path}' has value "
                        f"{record.value}, outside accepted bounds {accepted_bounds}."
                    ),
                    impact="The evaluation result contains a mathematically invalid metric value and cannot be trusted as reported.",
                    recommendation="Correct the metric computation or declare the correct unit and bounds before publishing the result.",
                    locations=[
                        Location(
                            role="primary",
                            path=record.artifact_path,
                            field=record.field_path,
                        )
                    ],
                    evidence={
                        "result_artifact": record.artifact_path,
                        "metric_name": record.metric_name,
                        "observed_value": record.value,
                        "accepted_bounds": accepted_bounds,
                        "unit": record.unit,
                        "field_path": record.field_path,
                    },
                )
            )

        return findings