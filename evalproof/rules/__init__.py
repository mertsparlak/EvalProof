"""Register built-in MVP contamination rules."""

from evalproof.rule_engine import default_registry
from evalproof.rules.train_eval_overlap import TrainEvalOverlapRule
from evalproof.rules.duplicate_eval_sample import DuplicateEvalSampleRule
from evalproof.rules.rag_answer_leakage import RagAnswerLeakageRule
from evalproof.rules.missing_repro_metadata import MissingReproMetadataRule
from evalproof.rules.fingerprint_mismatch import FingerprintMismatchRule
from evalproof.rules.untrusted_context_interpolation import UntrustedContextInterpolationRule
from evalproof.rules.sensitive_value_exposure import SensitiveValueExposureRule
from evalproof.rules.train_eval_near_duplicate import TrainEvalNearDuplicateRule
from evalproof.rules.duplicate_eval_near_duplicate import DuplicateEvalNearDuplicateRule
from evalproof.rules.duplicate_train_sample import DuplicateTrainSampleRule
from evalproof.rules.duplicate_train_near_duplicate import DuplicateTrainNearDuplicateRule
from evalproof.rules.sample_alignment_mismatch import SampleAlignmentMismatchRule
from evalproof.rules.label_inconsistency import LabelInconsistencyRule
from evalproof.rules.metric_out_of_bounds import MetricOutOfBoundsRule
from evalproof.rules.unreachable_context_id import UnreachableContextIdRule
from evalproof.rules.unresolved_placeholder import UnresolvedPlaceholderRule
from evalproof.rules.sample_id_collision import SampleIdCollisionRule
from evalproof.rules.empty_evaluation_input import EmptyEvaluationInputRule
from evalproof.rules.empty_referenced_document import EmptyReferencedDocumentRule
from evalproof.rules.partial_sample_id_coverage import PartialSampleIdCoverageRule
from evalproof.rules.empty_or_corrupted_document import EmptyOrCorruptedDocumentRule
from evalproof.rules.duplicate_chunk_in_corpus import DuplicateChunkInCorpusRule
from evalproof.rules.schema_contract_violation import SchemaContractViolationRule
from evalproof.rules.chunk_id_collision import ChunkIdCollisionRule
from evalproof.rules.generation_without_seed import GenerationWithoutSeedRule
from evalproof.rules.invalid_text_encoding import InvalidTextEncodingRule
from evalproof.rules.provenance import RequiredProvenanceMetadataRule, ManifestFingerprintMismatchRule, LocalSourceUnresolvedRule


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
    default_registry.register(SampleAlignmentMismatchRule())
    default_registry.register(LabelInconsistencyRule())
    default_registry.register(MetricOutOfBoundsRule())
    default_registry.register(UnreachableContextIdRule())
    default_registry.register(UnresolvedPlaceholderRule())
    default_registry.register(SampleIdCollisionRule())
    default_registry.register(EmptyEvaluationInputRule())
    default_registry.register(EmptyReferencedDocumentRule())
    default_registry.register(PartialSampleIdCoverageRule())
    default_registry.register(EmptyOrCorruptedDocumentRule())
    default_registry.register(DuplicateChunkInCorpusRule())
    default_registry.register(SchemaContractViolationRule())
    default_registry.register(ChunkIdCollisionRule())
    default_registry.register(GenerationWithoutSeedRule())
    default_registry.register(InvalidTextEncodingRule())
    default_registry.register(RequiredProvenanceMetadataRule())
    default_registry.register(ManifestFingerprintMismatchRule())
    default_registry.register(LocalSourceUnresolvedRule())


register_mvp_rules()
