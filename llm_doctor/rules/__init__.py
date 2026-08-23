"""Register built-in MVP contamination rules."""

from llm_doctor.rule_engine import default_registry
from llm_doctor.rules.train_eval_overlap import TrainEvalOverlapRule
from llm_doctor.rules.duplicate_eval_sample import DuplicateEvalSampleRule
from llm_doctor.rules.rag_answer_leakage import RagAnswerLeakageRule
from llm_doctor.rules.missing_repro_metadata import MissingReproMetadataRule
from llm_doctor.rules.fingerprint_mismatch import FingerprintMismatchRule
from llm_doctor.rules.untrusted_context_interpolation import UntrustedContextInterpolationRule
from llm_doctor.rules.sensitive_value_exposure import SensitiveValueExposureRule
from llm_doctor.rules.train_eval_near_duplicate import TrainEvalNearDuplicateRule
from llm_doctor.rules.duplicate_eval_near_duplicate import DuplicateEvalNearDuplicateRule
from llm_doctor.rules.duplicate_train_sample import DuplicateTrainSampleRule
from llm_doctor.rules.duplicate_train_near_duplicate import DuplicateTrainNearDuplicateRule


def register_mvp_rules():
    default_registry.register(TrainEvalOverlapRule())
    default_registry.register(DuplicateEvalSampleRule())
    default_registry.register(RagAnswerLeakageRule())
    default_registry.register(MissingReproMetadataRule())
    default_registry.register(FingerprintMismatchRule())
    default_registry.register(UntrustedContextInterpolationRule())
    default_registry.register(SensitiveValueExposureRule())
    default_registry.register(TrainEvalNearDuplicateRule())
    default_registry.register(DuplicateEvalNearDuplicateRule())
    default_registry.register(DuplicateTrainSampleRule())
    default_registry.register(DuplicateTrainNearDuplicateRule())


register_mvp_rules()
