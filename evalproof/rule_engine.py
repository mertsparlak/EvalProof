"""Rule Engine framework, ScanContext, Rule interface, Registry, and execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple, Any

from evalproof.artifact import Artifact
from evalproof.config import Config
from evalproof.finding import Finding, Diagnostic, DiagnosticSeverity, DiagnosticCode, Severity
from evalproof.project_index import ProjectIndex


@dataclass
class ScanContext:
    scan_root: str
    config: Config
    artifacts: Dict[str, Artifact]
    project_index: ProjectIndex
    diagnostics: List[Diagnostic] = field(default_factory=list)


class Rule(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Stable rule identifier namespaced by family (e.g. contamination.train_eval_overlap)."""
        pass

    @property
    @abstractmethod
    def title(self) -> str:
        """Short human-readable summary of the rule."""
        pass

    @property
    @abstractmethod
    def default_severity(self) -> str:
        """Default severity level: critical, high, medium, low."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description of what the rule checks."""
        pass

    @property
    @abstractmethod
    def artifact_roles(self) -> List[str]:
        """Artifact roles applicable to this rule."""
        pass

    @property
    @abstractmethod
    def tags(self) -> List[str]:
        """Categorization tags."""
        pass

    @abstractmethod
    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        """Execute rule logic against the scan context and return findings."""
        pass


class RuleSelectionError(ValueError):
    """Raised when a requested rule selection cannot be resolved."""

    pass


class RuleRegistry:
    def __init__(self):
        self._rules: Dict[str, Rule] = {}

    def register(self, rule: Rule):
        self._rules[rule.id] = rule

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        return self._rules.get(rule_id)

    def get_all_rules(self) -> List[Rule]:
        return sorted(self._rules.values(), key=lambda rule: rule.id)

    def get_enabled_rules(self, config: Config, selected_rule_ids: Optional[Iterable[str]] = None) -> List[Rule]:
        disabled_set = set(config.disabled_rules)
        all_rules = self.get_all_rules()

        if selected_rule_ids is None:
            candidates = all_rules
        else:
            selected_ids = list(selected_rule_ids)
            known_ids = {rule.id for rule in all_rules}
            unknown_ids = sorted(set(selected_ids) - known_ids)
            if unknown_ids:
                raise RuleSelectionError("Unknown rule id(s): " + ", ".join(unknown_ids))
            selected_set = set(selected_ids)
            candidates = [rule for rule in all_rules if rule.id in selected_set]

        enabled_rules = [rule for rule in candidates if rule.id not in disabled_set]
        if selected_rule_ids is not None and not enabled_rules:
            raise RuleSelectionError("Rule selection resolved to no enabled rules.")
        return enabled_rules


default_registry = RuleRegistry()


def execute_rules(
    ctx: ScanContext,
    registry: Optional[RuleRegistry] = None,
    selected_rule_ids: Optional[Iterable[str]] = None,
) -> Tuple[List[Finding], List[Diagnostic]]:
    """Execute all enabled rules, apply severity overrides, and collect findings & diagnostics."""
    if registry is None:
        registry = default_registry

    enabled_rules = registry.get_enabled_rules(ctx.config, selected_rule_ids=selected_rule_ids)
    findings: List[Finding] = []
    diagnostics: List[Diagnostic] = list(ctx.diagnostics)

    for rule in enabled_rules:
        try:
            rule_findings = rule.evaluate(ctx)
            for f in rule_findings:
                # Apply severity override if configured
                if f.rule_id in ctx.config.rule_severities:
                    override_sev = ctx.config.rule_severities[f.rule_id]
                    f.severity = override_sev
                    f.fingerprint = f.compute_fingerprint()
                findings.append(f)
        except Exception as err:
            diag = Diagnostic(
                severity=DiagnosticSeverity.ERROR.value,
                code=DiagnosticCode.RULE_RECOVERABLE_ERROR.value,
                message=f"Rule '{rule.id}' encountered a recoverable execution error: {err}",
                details={"rule_id": rule.id, "error": str(err)},
            )
            diagnostics.append(diag)

    return findings, diagnostics
