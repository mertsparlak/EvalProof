"""contamination.duplicate_eval_near_duplicate rule implementation."""

from typing import Any, Dict, List, Set, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import cap_evidence_items

RULE_ID = "contamination.duplicate_eval_near_duplicate"


def _sample_sort_key(sample: Dict[str, Any]) -> tuple:
    return (
        sample["source_path"],
        sample["source_row"],
        sample["target_path"],
        sample["target_row"],
        -sample["similarity_score"],
    )


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
        candidates = ctx.project_index.get_similarity_candidates(threshold=threshold)
        eval_roles = {"evaluation_dataset", "benchmark_dataset"}
        groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        emitted_pairs: Set[Tuple[str, str]] = set()

        for cand in candidates:
            src_meta = cand.metadata.get("source_metadata", {})
            tgt_meta = cand.metadata.get("target_metadata", {})
            src_roles = set(src_meta.get("roles", []))
            tgt_roles = set(tgt_meta.get("roles", []))
            if not (src_roles.intersection(eval_roles) and tgt_roles.intersection(eval_roles)):
                continue

            exact_hash_src = src_meta.get("exact_hash")
            exact_hash_tgt = tgt_meta.get("exact_hash")
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

            source, target = (path_a, row_a), (path_b, row_b)
            if source > target:
                source, target = target, source
            artifact_pair = tuple(sorted(set((path_a, path_b))))
            sample = {
                "source_path": source[0],
                "source_row": source[1],
                "target_path": target[0],
                "target_row": target[1],
                "similarity_score": sim_score,
            }
            group = groups.setdefault(
                artifact_pair,
                {"pairs": {}, "rows": set(), "max_similarity_score": sim_score},
            )
            sample_key = (
                sample["source_path"], sample["source_row"],
                sample["target_path"], sample["target_row"],
            )
            group["pairs"][sample_key] = sample
            group["rows"].update({(path_a, row_a), (path_b, row_b)})
            group["max_similarity_score"] = max(group["max_similarity_score"], sim_score)

        findings: List[Finding] = []
        for artifact_pair in sorted(groups):
            group = groups[artifact_pair]
            all_pairs = sorted(group["pairs"].values(), key=_sample_sort_key)
            sample_pairs, evidence_truncated = cap_evidence_items(all_pairs)
            first = all_pairs[0]
            path_a = artifact_pair[0]
            path_b = artifact_pair[-1]
            loc_a = Location(role="primary", path=path_a, row=first["source_row"] if first["source_path"] == path_a else first["target_row"])
            loc_b = Location(role="secondary", path=path_b, row=first["target_row"] if first["target_path"] == path_b else first["source_row"])
            max_score = group["max_similarity_score"]
            evidence = {
                "artifact_paths": list(artifact_pair),
                "near_duplicate_pair_count": len(all_pairs),
                "affected_row_count": len(group["rows"]),
                "max_similarity_score": max_score,
                "configured_threshold": threshold,
                "sample_pairs": sample_pairs,
                "evidence_truncated": evidence_truncated,
                "artifact_path": path_a,
                "evaluation_row": first["target_row"],
                "duplicate_row": first["source_row"],
                "similarity_score": max_score,
            }
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.LIKELY.value,
                    title=self.title,
                    message=(
                        f"Near-duplicate evaluation records found in {len(artifact_pair)} artifact(s): "
                        f"{len(all_pairs)} candidate pairs across {len(group['rows'])} rows "
                        f"(highest similarity score: {max_score:.4f})."
                    ),
                    impact="Near-duplicate samples can overweight repeated cases and distort evaluation metrics.",
                    recommendation="Deduplicate or rewrite near-duplicate evaluation samples.",
                    locations=[loc_a, loc_b],
                    evidence=evidence,
                )
            )

        return findings
