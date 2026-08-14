"""Rule: contamination.fingerprint_mismatch"""

from typing import Any, List

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.project_index import normalize_fingerprint
from evalproof.rule_engine import Rule, ScanContext


class FingerprintMismatchRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.fingerprint_mismatch"

    @property
    def title(self) -> str:
        return "Fingerprint mismatch detected"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects mismatch between referenced prompt or dataset fingerprints and available artifact fingerprints when both sides provide comparable values."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_result", "prompt_template", "evaluation_dataset", "training_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "fingerprint_mismatch"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        result_arts = sorted(
            ctx.project_index.artifacts_by_role.get("evaluation_result", []),
            key=lambda artifact: artifact.path,
        )
        prompt_roles = {"prompt_template"}
        dataset_roles = {"evaluation_dataset", "benchmark_dataset", "training_dataset"}

        for res_art in result_arts:
            meta = ctx.project_index.eval_metadata.get(res_art.path, {})
            ref_prompt_fp = meta.get("prompt_fingerprint")
            ref_dataset_fp = meta.get("dataset_fingerprint")

            if ref_prompt_fp:
                matches = ctx.project_index.matching_artifacts_for_fingerprint(ref_prompt_fp, prompt_roles)
                if not matches:
                    findings.append(
                        self._build_mismatch_finding(
                            result_path=res_art.path,
                            referenced_fp=ref_prompt_fp,
                            artifact_paths=sorted(
                                artifact.path
                                for artifact in ctx.project_index.artifacts_by_path.values()
                                if "prompt_template" in artifact.roles
                            ),
                            artifact_type="prompt",
                        )
                    )

            if ref_dataset_fp:
                matches = ctx.project_index.matching_artifacts_for_fingerprint(ref_dataset_fp, dataset_roles)
                if not matches:
                    findings.append(
                        self._build_mismatch_finding(
                            result_path=res_art.path,
                            referenced_fp=ref_dataset_fp,
                            artifact_paths=sorted(
                                artifact.path
                                for artifact in ctx.project_index.artifacts_by_path.values()
                                if dataset_roles.intersection(artifact.roles)
                                and "configuration" not in artifact.roles
                            ),
                            artifact_type="dataset",
                        )
                    )

        return findings

    def _build_mismatch_finding(
        self,
        result_path: str,
        referenced_fp: Any,
        artifact_paths: List[str],
        artifact_type: str,
    ) -> Finding:
        evidence = {
            "result_artifact": result_path,
            "referenced_fingerprint": str(referenced_fp),
            "candidate_artifact_paths": artifact_paths,
            "artifact_type": artifact_type,
        }
        return Finding(
            rule_id=self.id,
            severity=self.default_severity,
            confidence=Confidence.CONFIRMED.value,
            title=self.title,
            message=f"Referenced {artifact_type} fingerprint in '{result_path}' does not match any available {artifact_type} artifact.",
            impact=f"The evaluation result may not correspond to the available {artifact_type} artifact.",
            recommendation="Update references, restore the correct artifact version, or regenerate the result.",
            locations=[Location(role="primary", path=result_path)],
            evidence=evidence,
        )