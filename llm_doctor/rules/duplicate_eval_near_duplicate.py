"""contamination.duplicate_eval_near_duplicate rule implementation."""

from typing import List, Set, Tuple, Dict, Any
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

        eval_roles = {"evaluation_dataset", "benchmark_dataset"}
        eval_groups: Dict[Tuple[str, int], Dict[str, Any]] = {}
        emitted_pairs: Set[Tuple[str, str]] = set()

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

            pair_key = (min(cand.source_id, cand.target_id), max(cand.source_id, cand.target_id))
            if pair_key in emitted_pairs:
                continue
            emitted_pairs.add(pair_key)

            eval_key = (path_b, row_b)
            if eval_key not in eval_groups:
                eval_groups[eval_key] = {
                    "path": path_b,
                    "row": row_b,
                    "text": cand.target_text,
                    "max_similarity_score": sim_score,
                    "matched_records": [],
                    "seen_sources": set(),
                }

            group = eval_groups[eval_key]
            src_key = (path_a, row_a)
            if src_key not in group["seen_sources"]:
                group["seen_sources"].add(src_key)
                group["matched_records"].append({
                    "path": path_a,
                    "row": row_a,
                    "similarity_score": sim_score,
                    "configured_threshold": threshold,
                    "snippet": cand.source_text[:200],
                })
                if sim_score > group["max_similarity_score"]:
                    group["max_similarity_score"] = sim_score

        findings: List[Finding] = []
        for (path_b, row_b), group in eval_groups.items():
            matched = group["matched_records"]
            first_match = matched[0]
            path_a = first_match["path"]
            row_a = first_match["row"]
            sim_score = group["max_similarity_score"]
            match_count = len(matched)

            loc_b = Location(role="primary", path=path_b, row=row_b)
            loc_a = Location(role="secondary", path=path_a, row=row_a)

            if match_count == 1:
                msg = f"Near-duplicate evaluation record at row {row_b} resembles row {row_a} in '{path_a}' with similarity score {sim_score:.4f}."
            else:
                msg = f"Near-duplicate evaluation record at row {row_b} in '{path_b}' resembles {match_count} evaluation records (highest similarity score: {sim_score:.4f})."

            finding = Finding(
                rule_id=self.id,
                severity=self.default_severity,
                confidence=Confidence.LIKELY.value,
                title=self.title,
                message=msg,
                impact="Duplicate or near-duplicate evaluation samples skew evaluation metrics by over-weighting specific test cases.",
                recommendation="Deduplicate evaluation samples to ensure fair and unweighted evaluation metrics.",
                locations=[loc_b, loc_a],
                evidence={
                    "artifact_path": path_b,
                    "evaluation_row": row_b,
                    "duplicate_row": row_a,
                    "similarity_score": sim_score,
                    "configured_threshold": threshold,
                    "overlap_count": match_count,
                    "evaluation_snippet": group["text"][:200],
                    "duplicate_snippet": first_match["snippet"],
                    "matched_duplicate_records": matched,
                },
            )
            findings.append(finding)

        return findings
