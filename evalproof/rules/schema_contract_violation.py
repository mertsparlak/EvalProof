"""Rule: dataset.schema_contract_violation."""

from __future__ import annotations

from collections import Counter
import hashlib
import math
from typing import Any, Dict, List

from evalproof.config import ArtifactSchemaContract
from evalproof.finding import Confidence, DiagnosticCode, Finding, Location, Severity, canonical_json_dumps
from evalproof.rule_engine import Rule, ScanContext


RULE_ID = "dataset.schema_contract_violation"
MAX_EVIDENCE_VIOLATIONS = 20


class SchemaContractViolationRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Declared dataset schema contract violated"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Validates indexed dataset records against an explicit artifact schema contract."

    @property
    def artifact_roles(self) -> List[str]:
        return ["training_dataset", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return [
            "dataset_integrity",
            "schema_contract",
            "training_integrity",
            "evaluation_integrity",
        ]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        contracts = {
            override.path: override.schema
            for override in ctx.config.artifacts
            if override.schema is not None
        }
        findings: List[Finding] = []

        for artifact_path in sorted(contracts):
            artifact = ctx.project_index.artifacts_by_path.get(artifact_path)
            if artifact is None:
                continue
            contract = contracts[artifact_path]
            assert contract is not None
            violations = self._collect_violations(ctx, artifact_path, contract)
            if not violations:
                continue

            violations.sort(
                key=lambda item: (
                    item.get("row") or 0,
                    item.get("field") or "",
                    item["violation_type"],
                )
            )
            sample_violations = violations[:MAX_EVIDENCE_VIOLATIONS]
            violation_counts = dict(
                sorted(Counter(item["violation_type"] for item in violations).items())
            )
            affected_rows = {
                item["row"] for item in violations if item.get("row") is not None
            }

            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Artifact '{artifact_path}' has {len(violations)} violation(s) "
                        "of its declared dataset schema contract."
                    ),
                    impact=(
                        "Records that violate the declared schema can be dropped, misread, or passed "
                        "to training and evaluation code with unintended field semantics."
                    ),
                    recommendation=(
                        "Correct the affected records or update the explicit artifact schema contract "
                        "to match the intended dataset structure."
                    ),
                    locations=[
                        Location(
                            role="primary",
                            path=artifact_path,
                            row=item.get("row"),
                            field=item.get("field"),
                        )
                        for item in sample_violations
                    ],
                    evidence={
                        "artifact_path": artifact_path,
                        "contract_fingerprint": self._contract_fingerprint(contract),
                        "total_violation_count": len(violations),
                        "affected_row_count": len(affected_rows),
                        "violation_counts": violation_counts,
                        "sample_violations": sample_violations,
                        "evidence_truncated": len(violations) > MAX_EVIDENCE_VIOLATIONS,
                    },
                )
            )

        return findings

    def _collect_violations(
        self,
        ctx: ScanContext,
        artifact_path: str,
        contract: ArtifactSchemaContract,
    ) -> List[Dict[str, Any]]:
        artifact = ctx.project_index.artifacts_by_path[artifact_path]
        violations: List[Dict[str, Any]] = []
        artifact_parse_failed = False

        for diagnostic in artifact.diagnostics:
            if diagnostic.code == DiagnosticCode.ARTIFACT_PARSE_FAILED.value:
                artifact_parse_failed = True
                violations.append({"violation_type": "artifact_unparseable"})
            elif diagnostic.code == DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value:
                violation: Dict[str, Any] = {"violation_type": "record_unparseable"}
                if diagnostic.row is not None:
                    violation["row"] = diagnostic.row
                violations.append(violation)

        if artifact_parse_failed:
            return violations

        if artifact_path not in ctx.project_index.rows_by_artifact:
            violations.append({"violation_type": "record_collection_unavailable"})
            return violations

        for row in ctx.project_index.rows_by_artifact[artifact_path]:
            if not isinstance(row.row_data, dict):
                violations.append(
                    {
                        "row": row.row_num,
                        "row_hash": row.row_hash,
                        "violation_type": "record_not_object",
                    }
                )
                continue

            for field_name in sorted(contract.required):
                if field_name not in row.row_data:
                    violations.append(
                        {
                            "row": row.row_num,
                            "field": field_name,
                            "row_hash": row.row_hash,
                            "violation_type": "required_field_missing",
                            "expected_type": contract.fields[field_name].type,
                        }
                    )

            for field_name, field_contract in sorted(contract.fields.items()):
                if field_name not in row.row_data:
                    continue
                value = row.row_data[field_name]
                if value is None:
                    if not field_contract.nullable:
                        violations.append(
                            {
                                "row": row.row_num,
                                "field": field_name,
                                "row_hash": row.row_hash,
                                "violation_type": "null_not_allowed",
                                "expected_type": field_contract.type,
                                "observed_type": "null",
                            }
                        )
                    continue
                if not self._matches_type(value, field_contract.type):
                    violations.append(
                        {
                            "row": row.row_num,
                            "field": field_name,
                            "row_hash": row.row_hash,
                            "violation_type": "type_mismatch",
                            "expected_type": field_contract.type,
                            "observed_type": self._observed_type(value),
                        }
                    )

        return violations

    @staticmethod
    def _matches_type(value: Any, expected_type: str) -> bool:
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        return False

    @staticmethod
    def _observed_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number" if math.isfinite(value) else "non_finite_number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        return "unknown"

    @staticmethod
    def _contract_fingerprint(contract: ArtifactSchemaContract) -> str:
        payload = {
            "required": sorted(contract.required),
            "fields": {
                field_name: {
                    "type": field_contract.type,
                    "nullable": field_contract.nullable,
                }
                for field_name, field_contract in sorted(contract.fields.items())
            },
        }
        digest = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"
