"""Unit tests for the Similarity Engine (MinHash + LSH)."""

import pytest
from llm_doctor.config import Config, SimilarityConfig
from llm_doctor.similarity import (
    normalize_similarity_text,
    extract_shingles,
    compute_minhash_signature,
    compute_exact_jaccard,
    SimilarityCandidate,
    SimilarityIndex,
)


def test_normalize_similarity_text():
    assert normalize_similarity_text("  Hello, World!  ") == "hello world"
    assert normalize_similarity_text("FOO   BAR!!! 123") == "foo bar 123"
    assert normalize_similarity_text("") == ""


def test_extract_shingles():
    shingles = extract_shingles("hello", shingle_size=3)
    assert shingles == {"hel", "ell", "llo"}

    # Short string fallback
    short_shingles = extract_shingles("hi", shingle_size=3)
    assert short_shingles == {"hi"}

    assert extract_shingles("", shingle_size=3) == set()


def test_minhash_signature_determinism():
    shingles = extract_shingles("The quick brown fox jumps over the lazy dog", shingle_size=3)
    sig1 = compute_minhash_signature(shingles, num_hashes=64, seed=42)
    sig2 = compute_minhash_signature(shingles, num_hashes=64, seed=42)
    assert len(sig1) == 64
    assert sig1 == sig2


def test_exact_jaccard_computation():
    a = {"hel", "ell", "llo"}
    b = {"hel", "ell", "llo"}
    c = {"abc", "def"}

    assert compute_exact_jaccard(a, b) == 1.0
    assert compute_exact_jaccard(a, c) == 0.0
    assert compute_exact_jaccard(set(), set()) == 1.0


def test_similarity_index_add_and_query():
    idx = SimilarityIndex(shingle_size=3, num_hashes=64, bands=16, threshold=0.70, seed=42)

    doc1 = "The quick brown fox jumps over the lazy dog."
    doc2 = "The quick brown fox jumps over a lazy dog!"
    doc3 = "Quantum computing uses qubits for parallel computation."

    idx.add_item("doc1", doc1, metadata={"role": "train"})
    idx.add_item("doc2", doc2, metadata={"role": "eval"})
    idx.add_item("doc3", doc3, metadata={"role": "eval"})

    # Query with doc1
    results = idx.query_item(doc1, threshold=0.70)
    assert len(results) > 0
    # doc1 should match doc1 with 1.0 similarity and doc2 with high similarity
    target_ids = [r.target_id for r in results]
    assert "doc1" in target_ids
    assert "doc2" in target_ids
    assert "doc3" not in target_ids


def test_similarity_index_find_all_pairs():
    idx = SimilarityIndex(shingle_size=3, num_hashes=64, bands=16, threshold=0.70, seed=42)

    doc1 = "Artificial intelligence is transforming modern software engineering."
    doc2 = "Artificial intelligence is transforming modern software engineering!"
    doc3 = "Cooking traditional pasta requires fresh basil and tomatoes."

    idx.add_item("d1", doc1)
    idx.add_item("d2", doc2)
    idx.add_item("d3", doc3)

    pairs = idx.find_all_pairs(threshold=0.80)
    assert len(pairs) == 1
    pair = pairs[0]
    assert (pair.source_id == "d1" and pair.target_id == "d2") or (pair.source_id == "d2" and pair.target_id == "d1")
    assert pair.jaccard_similarity >= 0.80


def test_similarity_index_find_cross_role_pairs():
    idx = SimilarityIndex(shingle_size=3, num_hashes=64, bands=16, threshold=0.70, seed=42)

    text1 = "Prompt injection attack vector via untrusted context interpolation."
    text2 = "Prompt injection attack vector via untrusted context interpolation!"

    idx.add_item("train1", text1, metadata={"roles": ["training_dataset"]})
    idx.add_item("eval1", text2, metadata={"roles": ["evaluation_dataset"]})

    cross_pairs = idx.find_cross_role_pairs("training_dataset", "evaluation_dataset", threshold=0.80)
    assert len(cross_pairs) == 1
    pair = cross_pairs[0]
    assert pair.source_id == "train1"
    assert pair.target_id == "eval1"
    assert pair.jaccard_similarity >= 0.80


def test_similarity_candidate_to_dict():
    cand = SimilarityCandidate(
        source_id="src",
        target_id="tgt",
        source_text="hello",
        target_text="hello world",
        jaccard_similarity=0.85,
        metadata={"foo": "bar"},
    )
    d = cand.to_dict()
    assert d["source_id"] == "src"
    assert d["target_id"] == "tgt"
    assert d["jaccard_similarity"] == 0.85
    assert d["metadata"]["foo"] == "bar"


def test_similarity_config_integration():
    cfg = Config()
    assert cfg.similarity.enabled is True
    assert cfg.similarity.shingle_size == 3
    assert cfg.similarity.num_hashes == 64
    assert cfg.similarity.bands == 16
    assert cfg.similarity.threshold == 0.85
