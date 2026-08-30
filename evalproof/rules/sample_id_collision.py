"""Rule: dataset.sample_id_collision."""

import hashlib
from collections import defaultdict
from typing import Dict, List, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import SAMPLE_ID_FIELD_ALIASES, extract_scalar_field
from evalproof.rule_engine import Rule, ScanContext


RULE_ID = "dataset.sample_id_collision"


class SampleIdCollisionRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Duplicate sample ID in evaluation dataset"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects one explicit sample ID assigned to multiple rows in an evaluation or benchmark artifact."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["dataset_integrity", "sample_identity", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        grouped: Dict[Tuple[str, str], List[Tuple[str, int, str, str]]] = defaultdict(list)
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not {"evaluation_dataset", "benchmark_dataset"}.intersection(artifact.roles):
                continue
            for row in ctx.project_index.rows_by_artifact.get(artifact.path, []):
                extracted = extract_scalar_field(row.row_data, SAMPLE_ID_FIELD_ALIASES)
                if extracted is None:
                    continue
                field_name, identifier = extracted
                grouped[(artifact.path, identifier)].append(
                    (artifact.path, row.row_num, field_name, row.row_hash)
                )

        findings: List[Finding] = []
        for (artifact_path, identifier), rows in sorted(grouped.items()):
            if len(rows) < 2:
                continue
            row_locations = [
                {"path": path, "row": row_num}
                for path, row_num, _, _ in rows
            ]
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=f"Artifact '{artifact_path}' assigns one sample ID to {len(rows)} rows.",
                    impact="Duplicate sample identities make evaluation results ambiguous and can duplicate or overwrite sample-level results.",
                    recommendation="Assign one stable, unique sample ID to each evaluation row and regenerate dependent result artifacts.",
                    locations=[
                        Location(role="primary", path=path, row=row_num)
                        for path, row_num, _, _ in rows
                    ],
                    evidence={
                        "artifact_path": artifact_path,
                        "sample_id_fields": sorted({field_name for _, _, field_name, _ in rows}),
                        "sample_id_hash": f"sha256:{hashlib.sha256(identifier.encode('utf-8')).hexdigest()}",
                        "row_locations": row_locations,
                        "row_hashes": [row_hash for _, _, _, row_hash in rows],
                        "duplicate_count": len(rows),
                        "distinct_content_count": len({row_hash for _, _, _, row_hash in rows}),
                    },
                )
            )
        return findings
