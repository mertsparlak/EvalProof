"""Rule: contamination.fingerprint_mismatch"""

from typing import Any, List, Optional

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.rule_engine import Rule, ScanContext


def normalize_fp(fp: Any) -> str:
    s = str(fp).strip().lower()
    if s.startswith("sha256:"):
        return s[7:]
    return s


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
        result_arts = ctx.project_index.artifacts_by_role.get("evaluation_result", [])
        prompt_arts = ctx.project_index.artifacts_by_role.get("prompt_template", [])
        candidate_dataset_arts = ctx.project_index.artifacts_by_role.get("evaluation_dataset", []) + \
                       ctx.project_index.artifacts_by_role.get("benchmark_dataset", []) + \
                       ctx.project_index.artifacts_by_role.get("training_dataset", [])
        dataset_arts = [art for art in candidate_dataset_arts if "configuration" not in art.roles]

        if not result_arts:
            return findings

        for res_art in result_arts:
            meta = ctx.project_index.eval_metadata.get(res_art.path, {})
            ref_prompt_fp = meta.get("prompt_fingerprint")
            ref_dataset_fp = meta.get("dataset_fingerprint")

            # Check prompt template fingerprint mismatch
            if ref_prompt_fp:
                norm_ref_prompt = normalize_fp(ref_prompt_fp)
                for p_art in prompt_arts:
                    comp_fp = ctx.project_index.artifact_fingerprints.get(p_art.path)
                    if comp_fp:
                        norm_comp = normalize_fp(comp_fp)
                        if norm_ref_prompt != norm_comp:
                            loc_primary = Location(role="primary", path=res_art.path)
                            loc_related = Location(role="related", path=p_art.path)
                            finding = Finding(
                                rule_id=self.id,
                                severity=self.default_severity,
                                confidence=Confidence.CONFIRMED.value,
                                title=self.title,
                                message=f"Referenced prompt fingerprint in '{res_art.path}' differs from computed fingerprint of prompt artifact '{p_art.path}'.",
                                impact="The evaluation result may not correspond to the available prompt template artifact.",
                                recommendation="Update references, restore the correct artifact version, or regenerate the result.",
                                locations=[loc_primary, loc_related],
                                evidence={
                                    "result_artifact": res_art.path,
                                    "referenced_fingerprint": str(ref_prompt_fp),
                                    "computed_fingerprint": str(comp_fp),
                                    "related_artifact_path": p_art.path,
                                },
                            )
                            findings.append(finding)

            # Check dataset fingerprint mismatch
            if ref_dataset_fp:
                norm_ref_ds = normalize_fp(ref_dataset_fp)
                for d_art in dataset_arts:
                    comp_fp = ctx.project_index.artifact_fingerprints.get(d_art.path)
                    if comp_fp:
                        norm_comp = normalize_fp(comp_fp)
                        if norm_ref_ds != norm_comp:
                            loc_primary = Location(role="primary", path=res_art.path)
                            loc_related = Location(role="related", path=d_art.path)
                            finding = Finding(
                                rule_id=self.id,
                                severity=self.default_severity,
                                confidence=Confidence.CONFIRMED.value,
                                title=self.title,
                                message=f"Referenced dataset fingerprint in '{res_art.path}' differs from computed fingerprint of dataset artifact '{d_art.path}'.",
                                impact="The evaluation result may not correspond to the available dataset artifact.",
                                recommendation="Update references, restore the correct artifact version, or regenerate the result.",
                                locations=[loc_primary, loc_related],
                                evidence={
                                    "result_artifact": res_art.path,
                                    "referenced_fingerprint": str(ref_dataset_fp),
                                    "computed_fingerprint": str(comp_fp),
                                    "related_artifact_path": d_art.path,
                                },
                            )
                            findings.append(finding)

        return findings
