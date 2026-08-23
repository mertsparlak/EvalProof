"""Rule: contamination.missing_repro_metadata"""

from typing import List, Set

from llm_doctor.finding import Finding, Location, Severity, Confidence
from llm_doctor.rule_engine import Rule, ScanContext


class MissingReproMetadataRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.missing_repro_metadata"

    @property
    def title(self) -> str:
        return "Missing reproducibility metadata"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects evaluation result artifacts missing required reproducibility metadata."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_result"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "reproducibility"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        result_arts = ctx.project_index.artifacts_by_role.get("evaluation_result", [])

        for art in result_arts:
            meta = ctx.project_index.eval_metadata.get(art.path, {})

            missing_fields: List[str] = []

            # 1. model_id
            if "model_id" not in meta:
                missing_fields.append("model_id")

            # 2. generation_parameters
            if "generation_parameters" not in meta:
                missing_fields.append("generation_parameters")

            # 3. prompt_fingerprint or prompt_version
            if "prompt_fingerprint" not in meta and "prompt_version" not in meta:
                missing_fields.append("prompt_fingerprint_or_version")

            # 4. dataset_fingerprint or dataset_version
            if "dataset_fingerprint" not in meta and "dataset_version" not in meta:
                missing_fields.append("dataset_fingerprint_or_version")

            # 5. metric_name
            if "metric_name" not in meta:
                missing_fields.append("metric_name")

            # 6. metric_definition or metric_threshold
            if "metric_definition" not in meta and "metric_threshold" not in meta:
                missing_fields.append("metric_definition_or_threshold")

            # 7. timestamp
            if "timestamp" not in meta:
                missing_fields.append("timestamp")

            if missing_fields:
                loc = Location(role="primary", path=art.path)
                finding = Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=f"Evaluation result '{art.path}' is missing required reproducibility metadata fields: {missing_fields}.",
                    impact="The result cannot be reliably reproduced or compared later.",
                    recommendation="Add the missing metadata to the result artifact or regenerate the result with metadata capture enabled.",
                    locations=[loc],
                    evidence={
                        "result_artifact": art.path,
                        "missing_metadata_fields": missing_fields,
                    },
                )
                findings.append(finding)

        return findings
