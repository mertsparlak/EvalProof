"""contamination.duplicate_eval_near_duplicate rule implementation."""

from typing import List, Set, Tuple
from llm_doctor.finding import Finding, Severity, Confidence, Location
from llm_doctor.rule_engine import Rule, ScanContext

RULE_ID = "contamination.duplicate_eval_near_duplicate"


class DuplicateEvalNearDuplicateRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Near-duplicate evaluation record detected"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detect near-duplicate records within evaluation or benchmark datasets."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "near_duplicate", "duplicate_sample"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        if not ctx.config.similarity.enabled:
            return []

        threshold = ctx.config.similarity.threshold
        candidates = ctx.project_index.similarity_index.find_all_pairs(threshold=threshold)

        findings: List[Finding] = []
        emitted_pairs: Set[Tuple[str, str]] = set()

        eval_roles = {"evaluation_dataset", "benchmark_dataset"}

        for cand in candidates:
            src_meta = cand.metadata.get("source_metadata", {})
            tgt_meta = cand.metadata.get("target_metadata", {})

            src_roles = set(src_meta.get("roles", []))
            tgt_roles = set(tgt_meta.get("roles", []))

            # Both items must belong to evaluation or benchmark datasets
            if not (src_roles.intersection(eval_roles) and tgt_roles.intersection(eval_roles)):
                continue

            exact_hash_src = src_meta.get("exact_hash")
            exact_hash_tgt = tgt_meta.get("exact_hash")

            # Exact duplicates must NEVER produce near-duplicate findings
            if exact_hash_src and exact_hash_tgt and exact_hash_src == exact_hash_tgt:
                continue
            if cand.jaccard_similarity >= 1.0:
                continue

            sim_score = round(cand.jaccard_similarity, 4)
            if sim_score < threshold:
                continue

            path_a = src_meta.get("path", cand.source_id)
            row_a = src_meta.get("row_number", 1)
            path_b = tgt_meta.get("path", cand.target_id)
            row_b = tgt_meta.get("row_number", 1)

            # Prevent duplicate findings for symmetric pair
            pair_key = (min(cand.source_id, cand.target_id), max(cand.source_id, cand.target_id))
            if pair_key in emitted_pairs:
                continue
            emitted_pairs.add(pair_key)

            loc_b = Location(role="primary", path=path_b, row=row_b)
            loc_a = Location(role="secondary", path=path_a, row=row_a)

            finding = Finding(
                rule_id=self.id,
                severity=self.default_severity,
                confidence=Confidence.LIKELY.value,
                title=self.title,
                message=(
                    f"Near-duplicate evaluation record at row {row_b} resembles row {row_a} "
                    f"in '{path_b}' with similarity score {sim_score:.4f}."
                ),
                impact="Duplicate or near-duplicate evaluation samples skew evaluation metrics by over-weighting specific test cases.",
                recommendation="Deduplicate evaluation samples to ensure fair and unweighted evaluation metrics.",
                locations=[loc_b, loc_a],
                evidence={
                    "artifact_path": path_b,
                    "evaluation_row": row_b,
                    "duplicate_row": row_a,
                    "similarity_score": sim_score,
                    "evaluation_snippet": cand.target_text[:200],
                    "duplicate_snippet": cand.source_text[:200],
                },
            )
            findings.append(finding)

        return findings
