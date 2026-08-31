"""Advisory check for absent seed metadata in stochastic evaluation runs."""

import math

from evalproof.finding import Finding, Location
from evalproof.rule_engine import Rule


class GenerationWithoutSeedRule(Rule):
    @property
    def id(self):
        return "reproducibility.nondeterministic_generation_without_seed"

    @property
    def title(self):
        return "Positive sampling temperature without a recorded seed"

    @property
    def description(self):
        return "Flags explicit evaluation generation parameters with positive temperature and an absent seed."

    @property
    def default_severity(self):
        return "medium"

    @property
    def artifact_roles(self):
        return ["evaluation_result"]

    @property
    def tags(self):
        return ["reproducibility", "generation_metadata"]

    def evaluate(self, ctx):
        findings = []
        index = ctx.project_index
        for artifact in sorted(index.artifacts_by_role.get("evaluation_result", []), key=lambda art: art.path):
            if "configuration" in artifact.roles:
                continue
            parameters = index.eval_metadata.get(artifact.path, {}).get("generation_parameters")
            field = index.eval_metadata_locations.get(artifact.path, {}).get("generation_parameters")
            if not isinstance(parameters, dict) or not field:
                continue
            temperature = parameters.get("temperature")
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
                continue
            if temperature <= 0 or (isinstance(temperature, float) and not math.isfinite(temperature)):
                continue
            seed = parameters.get("seed")
            if "seed" not in parameters:
                state = "missing"
            elif seed is None:
                state = "null"
            elif isinstance(seed, str) and not seed.strip():
                state = "blank"
            else:
                continue
            findings.append(Finding(
                rule_id=self.id, severity=self.default_severity, confidence="likely",
                title=self.title,
                message="Positive sampling temperature is recorded without a non-blank seed in the same parameter object.",
                impact="Unrecorded sampling state may make evaluation runs harder to reproduce; actual runner behavior is not verified.",
                recommendation="Record a seed if supported by the runner, together with model and backend versions. A seed alone does not guarantee repeatability.",
                locations=[Location(role="primary", path=artifact.path, field=field + ".temperature")],
                evidence={
                    "result_artifact": artifact.path, "parameters_field": field,
                    "temperature_field": field + ".temperature", "observed_temperature": temperature,
                    "seed_field": field + ".seed", "seed_state": state,
                },
            ))
        return findings
