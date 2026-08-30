"""contamination.train_eval_near_duplicate rule implementation."""

from typing import List, Set, Tuple, Dict, Any
from evalproof.finding import Finding, Severity, Confidence, Location
from evalproof.rule_engine import Rule, ScanContext

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

        # Map: (eval_path, eval_row) -> aggregated match information
        eval_groups: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for cand in candidates:
            src_meta = cand.metadata.get("source_metadata", {})
            tgt_meta = cand.metadata.get("target_metadata", {})

            src_roles = set(src_meta.get("roles", []))
            tgt_roles = set(tgt_meta.get("roles", []))

            # One item must be train and the other must be eval/benchmark
            is_src_train = bool(src_roles.intersection(train_roles))
            is_src_eval = bool(src_roles.intersection(eval_roles))
            is_tgt_train = bool(tgt_roles.intersection(train_roles))
            is_tgt_eval = bool(tgt_roles.intersection(eval_roles))

            if is_src_train and is_tgt_eval:
                train_meta, train_text = src_meta, cand.source_text
                eval_meta, eval_text = tgt_meta, cand.target_text
            elif is_src_eval and is_tgt_train:
                train_meta, train_text = tgt_meta, cand.target_text
                eval_meta, eval_text = src_meta, cand.source_text
            else:
                continue

            exact_hash_train = train_meta.get("exact_hash")
            exact_hash_eval = eval_meta.get("exact_hash")

            # Exact duplicates must NEVER produce near-duplicate findings
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
            if eval_key not in eval_groups:
                eval_groups[eval_key] = {
                    "eval_path": eval_path,
                    "eval_row": eval_row,
                    "eval_text": eval_text,
                    "max_similarity_score": sim_score,
                    "matched_training_records": [],
                    "seen_train_keys": set(),
                }

            group = eval_groups[eval_key]
            train_key = (train_path, train_row)
            if train_key not in group["seen_train_keys"]:
                group["seen_train_keys"].add(train_key)
                group["matched_training_records"].append({
                    "path": train_path,
                    "row": train_row,
                    "similarity_score": sim_score,
                    "configured_threshold": threshold,
                    "snippet": train_text[:200],
                })
                if sim_score > group["max_similarity_score"]:
                    group["max_similarity_score"] = sim_score

        findings: List[Finding] = []
        for (eval_path, eval_row), group in eval_groups.items():
            matched_train = group["matched_training_records"]
            first_train = matched_train[0]
            train_path = first_train["path"]
            train_row = first_train["row"]
            sim_score = group["max_similarity_score"]
            match_count = len(matched_train)

            loc_target = Location(role="target", path=eval_path, row=eval_row)
            loc_source = Location(role="source", path=train_path, row=train_row)

            if match_count == 1:
                msg = (
                    f"Near-duplicate evaluation record in '{eval_path}' (row {eval_row}) resembles "
                    f"training record in '{train_path}' (row {train_row}) with similarity score {sim_score:.4f}."
                )
            else:
                msg = (
                    f"Near-duplicate evaluation record in '{eval_path}' (row {eval_row}) resembles "
                    f"{match_count} training records (highest similarity score: {sim_score:.4f})."
                )

            finding = Finding(
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
                    "training_artifact": train_path,
                    "training_row": train_row,
                    "similarity_score": sim_score,
                    "configured_threshold": threshold,
                    "overlap_count": match_count,
                    "evaluation_snippet": group["eval_text"][:200],
                    "training_snippet": first_train["snippet"],
                    "matched_training_records": matched_train,
                },
            )
            findings.append(finding)

        return findings
