"""contamination.train_eval_near_duplicate rule implementation."""

from typing import List, Set, Tuple
from llm_doctor.finding import Finding, Severity, Confidence, Location
from llm_doctor.rule_engine import Rule, ScanContext

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
        candidates = ctx.project_index.similarity_index.find_all_pairs(threshold=threshold)

        findings: List[Finding] = []
        emitted_pairs: Set[Tuple[str, str]] = set()

        train_roles = {"training_dataset"}
        eval_roles = {"evaluation_dataset", "benchmark_dataset"}

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

            pair_key = (f"{train_path}:{train_row}", f"{eval_path}:{eval_row}")
            if pair_key in emitted_pairs:
                continue
            emitted_pairs.add(pair_key)

            loc_source = Location(role="source", path=train_path, row=train_row)
            loc_target = Location(role="target", path=eval_path, row=eval_row)

            finding = Finding(
                rule_id=self.id,
                severity=self.default_severity,
                confidence=Confidence.LIKELY.value,
                title=self.title,
                message=(
                    f"Near-duplicate record in '{train_path}' (row {train_row}) also appears in "
                    f"'{eval_path}' (row {eval_row}) with similarity score {sim_score:.4f}."
                ),
                impact="Near-duplicate records between training and evaluation splits inflate evaluation scores due to data leakage.",
                recommendation="Remove or replace near-duplicate evaluation samples to ensure benchmark validity.",
                locations=[loc_source, loc_target],
                evidence={
                    "training_artifact": train_path,
                    "training_row": train_row,
                    "evaluation_artifact": eval_path,
                    "evaluation_row": eval_row,
                    "similarity_score": sim_score,
                    "training_snippet": train_text[:200],
                    "evaluation_snippet": eval_text[:200],
                },
            )
            findings.append(finding)

        return findings
