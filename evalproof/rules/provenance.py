"""Opt-in checks of explicit dataset provenance declarations."""

from dataclasses import asdict
import hashlib

from evalproof.finding import Finding, Location, canonical_json_dumps
from evalproof.rule_engine import Rule


def _contracts(ctx):
    for override in sorted(ctx.config.artifacts, key=lambda entry: entry.path):
        if override.provenance is not None and override.path in ctx.project_index.artifacts_by_path:
            yield override.path, override.provenance


class _ProvenanceRule(Rule):
    @property
    def artifact_roles(self):
        return ["training_dataset", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self):
        return ["provenance", "dataset_integrity"]

    def _finding(self, path, contract, evidence, message, impact, recommendation):
        declaration = asdict(contract)
        if declaration["card"] is None:
            declaration.pop("card")
        contract_hash = hashlib.sha256(canonical_json_dumps(declaration).encode("utf-8")).hexdigest()
        return Finding(
            rule_id=self.id, severity=self.default_severity, confidence="confirmed",
            title=self.title, message=message, impact=impact, recommendation=recommendation,
            locations=[Location(role="primary", path=path)],
            evidence={"artifact_path": path, "contract_fingerprint": "sha256:" + contract_hash, **evidence},
        )


class RequiredProvenanceMetadataRule(_ProvenanceRule):
    @property
    def id(self):
        return "provenance.required_metadata_missing"

    @property
    def title(self):
        return "Required provenance metadata is missing"

    @property
    def description(self):
        return "Checks only explicitly required provenance fields, without inferring lineage requirements."

    @property
    def default_severity(self):
        return "medium"

    def evaluate(self, ctx):
        findings = []
        for path, contract in _contracts(ctx):
            missing = []
            card_evidence = {}
            for name in contract.required:
                parent, separator, leaf = name.partition(".")
                value = getattr(contract, parent)
                if separator:
                    value = value.get(leaf)
                if value is None:
                    if name == "license" and contract.card is not None:
                        facts = ctx.project_index.dataset_cards.get(path)
                        if facts is None or facts["license_status"] != "missing":
                            continue
                        card_evidence = facts
                    missing.append(name)
            if missing:
                findings.append(self._finding(
                    path, contract, {"missing_fields": missing, "missing_count": len(missing), **card_evidence},
                    "Explicitly required provenance metadata is absent.",
                    "The dataset's declared lineage contract is incomplete.",
                    "Record the missing declared metadata fields; no additional provenance fields are inferred.",
                ))
        return findings


class ManifestFingerprintMismatchRule(_ProvenanceRule):
    @property
    def id(self):
        return "provenance.manifest_fingerprint_mismatch"

    @property
    def title(self):
        return "Declared dataset fingerprint does not match current content"

    @property
    def description(self):
        return "Compares a declared semantic dataset fingerprint with a completely indexed artifact."

    @property
    def default_severity(self):
        return "high"

    def evaluate(self, ctx):
        findings = []
        coverage = {entry["path"]: entry for entry in ctx.project_index.get_artifact_coverage([])}
        for path, contract in _contracts(ctx):
            observed = ctx.project_index.artifact_fingerprints.get(path)
            if not contract.fingerprint or not observed or coverage[path]["index_status"] != "indexed":
                continue
            if contract.fingerprint != observed:
                findings.append(self._finding(
                    path, contract, {"declared_fingerprint": contract.fingerprint, "observed_fingerprint": observed},
                    "Current dataset content does not match its declared semantic fingerprint.",
                    "The available dataset is not the content version named by the declaration.",
                    "Restore the intended dataset or update its fingerprint only after verifying the content change.",
                ))
        return findings


class LocalSourceUnresolvedRule(_ProvenanceRule):
    @property
    def id(self):
        return "provenance.local_source_unresolved"

    @property
    def title(self):
        return "Declared local source is not an available file"

    @property
    def description(self):
        return "Checks whether an explicitly declared local source is missing or is not a regular file."

    @property
    def default_severity(self):
        return "high"

    def evaluate(self, ctx):
        findings = []
        for path, contract in _contracts(ctx):
            facts = ctx.project_index.provenance_sources.get(path)
            if facts is None or facts["status"] not in {"missing", "not_file"}:
                continue
            findings.append(self._finding(
                path, contract, {"source_ref_hash": facts["source_ref_hash"], "source_status": facts["status"]},
                "Declared local source is missing or does not identify a regular file.",
                "The declared local source cannot be used to trace this dataset's origin.",
                "Restore the source file or correct the declared local source reference.",
            ))
        return findings
