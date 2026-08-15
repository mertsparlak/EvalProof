"""contamination.train_eval_near_duplicate rule implementation."""

from typing import Any, Dict, List, Set, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import cap_evidence_items

RULE_ID = "contamination.train_eval_near_duplicate"


class TrainEvalNearDuplicateRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Train/eval near-duplicate record overlap detected"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detect near-duplicate record overlap between training datasets and evaluation or benchmark datasets."

    @property
    def artifact_roles(self) -> List[str]:
        return ["training_dataset", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "near_duplicate", "split_leakage"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        if not ctx.config.similarity.enabled:
            return []

        threshold = ctx.config.similarity.threshold
        candidates = ctx.project_index.get_similarity_candidates(threshold=threshold)
        train_roles = {"training_dataset"}
        eval_roles = {"evaluation_dataset", "benchmark_dataset"}
        eval_groups: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for cand in candidates:
            src_meta = cand.metadata.get("source_metadata", {})
            tgt_meta = cand.metadata.get("target_metadata", {})
            src_roles = set(src_meta.get("roles", []))
            tgt_roles = set(tgt_meta.get("roles", []))

            is_src_train = bool(src_roles.intersection(train_roles))
            is_src_eval = bool(src_roles.intersection(eval_roles))
            is_tgt_train = bool(tgt_roles.intersection(train_roles))
            is_tgt_eval = bool(tgt_roles.intersection(eval_roles))
            if is_src_train and is_tgt_eval:
                train_meta, eval_meta = src_meta, tgt_meta
            elif is_src_eval and is_tgt_train:
                train_meta, eval_meta = tgt_meta, src_meta
            else:
                continue

            exact_hash_train = train_meta.get("exact_hash")
            exact_hash_eval = eval_meta.get("exact_hash")
            if exact_hash_train and exact_hash_eval and exact_hash_train == exact_hash_eval:
                continue
            if cand.jaccard_similarity >= 1.0:
                continue

            sim_score = round(cand.jaccard_similarity, 4)
            if sim_score < threshold:
                continue

            train_path = train_meta.get("path", "")
            train_row = train_meta.get("row_number", 1)
            eval_path = eval_meta.get("path", "")
            eval_row = eval_meta.get("row_number", 1)
            if train_path == eval_path:
                continue

            eval_key = (eval_path, eval_row)
            group = eval_groups.setdefault(
                eval_key,
                {"eval_path": eval_path, "eval_row": eval_row, "matches": {}, "max_similarity_score": sim_score},
            )
            train_key = (train_path, train_row)
            group["matches"][train_key] = {
                "path": train_path,
                "row": train_row,
                "similarity_score": sim_score,
                "configured_threshold": threshold,
            }
            group["max_similarity_score"] = max(group["max_similarity_score"], sim_score)

        findings: List[Finding] = []
        for eval_path, eval_row in sorted(eval_groups):
            group = eval_groups[(eval_path, eval_row)]
            all_matches = sorted(
                group["matches"].values(),
                key=lambda item: (item["path"], item["row"], -item["similarity_score"]),
            )
            matched_train, evidence_truncated = cap_evidence_items(all_matches)
            first_train = all_matches[0]
            sim_score = group["max_similarity_score"]
            match_count = len(all_matches)
            loc_target = Location(role="target", path=eval_path, row=eval_row)
            loc_source = Location(role="source", path=first_train["path"], row=first_train["row"])
            if match_count == 1:
                msg = (
                    f"Near-duplicate evaluation record in '{eval_path}' (row {eval_row}) resembles "
                    f"training record in '{first_train['path']}' (row {first_train['row']}) with similarity score {sim_score:.4f}."
                )
            else:
                msg = (
                    f"Near-duplicate evaluation record in '{eval_path}' (row {eval_row}) resembles "
                    f"{match_count} training records (highest similarity score: {sim_score:.4f})."
                )

            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.LIKELY.value,
                    title=self.title,
                    message=msg,
                    impact="Near-duplicate records between training and evaluation splits inflate evaluation scores due to data leakage.",
                    recommendation="Remove or replace near-duplicate evaluation samples to ensure benchmark validity.",
                    locations=[loc_target, loc_source],
                    evidence={
                        "evaluation_artifact": eval_path,
                        "evaluation_row": eval_row,
                        "training_artifact": first_train["path"],
                        "training_row": first_train["row"],
                        "similarity_score": sim_score,
                        "configured_threshold": threshold,
                        "overlap_count": match_count,
                        "matched_training_records": matched_train,
                        "evidence_truncated": evidence_truncated,
                    },
                )
            )

        return findings
