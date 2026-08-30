"""Rule: dataset.label_inconsistency."""

import hashlib
from collections import defaultdict
from typing import Dict, List, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import (
    ANSWER_FIELD_ALIASES,
    CONTEXT_FIELD_ALIASES,
    canonical_json_dumps,
    extract_scalar_field,
    normalize_plain_text,
    normalize_row_data,
)
from evalproof.rule_engine import Rule, ScanContext


INPUT_FIELD_ALIASES = ["prompt", "question", "input"]


class LabelInconsistencyRule(Rule):
    @property
    def id(self) -> str:
        return "dataset.label_inconsistency"

    @property
    def title(self) -> str:
        return "Conflicting labels for the same evaluation input"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects different target values assigned to the same normalized evaluation input and context."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["dataset_integrity", "labels", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        grouped: Dict[str, Dict[str, List[Tuple[str, int, str, str]]]] = defaultdict(lambda: defaultdict(list))
        for artifact in sorted(
            ctx.project_index.artifacts_by_path.values(),
            key=lambda item: item.path,
        ):
            if not {"evaluation_dataset", "benchmark_dataset"}.intersection(artifact.roles):
                continue
            for row in ctx.project_index.rows_by_artifact.get(artifact.path, []):
                input_field = extract_scalar_field(row.row_data, INPUT_FIELD_ALIASES)
                target_field = extract_scalar_field(row.row_data, ANSWER_FIELD_ALIASES)
                if input_field is None or target_field is None:
                    continue

                context_values = {
                    field: normalize_row_data(row.row_data[field])
                    for field in CONTEXT_FIELD_ALIASES
                    if isinstance(row.row_data, dict) and field in row.row_data
                }
                identity = {
                    "input": normalize_plain_text(input_field[1]),
                    "context": context_values,
                }
                identity_json = canonical_json_dumps(identity)
                input_hash = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()
                normalized_target = normalize_plain_text(target_field[1])
                grouped[input_hash][normalized_target].append(
                    (artifact.path, row.row_num, input_field[0], target_field[0])
                )

        findings: List[Finding] = []
        for input_hash in sorted(grouped):
            target_groups = grouped[input_hash]
            if len(target_groups) < 2:
                continue

            conflicting_rows = sorted(
                location
                for locations in target_groups.values()
                for location in locations
            )
            target_hashes = sorted(
                hashlib.sha256(target.encode("utf-8")).hexdigest()
                for target in target_groups
            )
            artifact_paths = sorted({location[0] for location in conflicting_rows})
            first_path = conflicting_rows[0][0]
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=f"Input hash {input_hash} has {len(target_groups)} conflicting target values.",
                    impact="Conflicting targets make the evaluation result ambiguous and reduce confidence in the benchmark labels.",
                    recommendation="Resolve the annotation conflict or include the missing context that distinguishes the examples.",
                    locations=[
                        Location(role="primary", path=path, row=row)
                        for path, row, _, _ in conflicting_rows
                    ],
                    evidence={
                        "artifact_paths": artifact_paths,
                        "normalized_input_hash": f"sha256:{input_hash}",
                        "input_field": conflicting_rows[0][2],
                        "target_fields": sorted({location[3] for location in conflicting_rows}),
                        "conflicting_target_count": len(target_groups),
                        "conflicting_target_hashes": target_hashes,
                        "row_locations": [
                            {"path": path, "row": row}
                            for path, row, _, _ in conflicting_rows
                        ],
                    },
                )
            )

        return findings