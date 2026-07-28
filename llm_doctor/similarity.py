"""Reusable deterministic Similarity Engine (MinHash + LSH) for EvalProof."""

from dataclasses import dataclass, field
import random
import re
from typing import Dict, List, Optional, Set, Tuple, Any


MERSENNE_PRIME = 2147483647  # 2^31 - 1


def extract_target_similarity_text(row_data: Any, similarity_config: Optional[Any] = None) -> str:
    """Extract targeted text from structured row data for similarity checks.

    Filters out static system instruction prompts by focusing on user messages
    or specific prompt/input fields.
    """
    if isinstance(row_data, str):
        return row_data

    focus_roles = set(getattr(similarity_config, "focus_roles", ["user"]) or ["user"])
    focus_fields = set(getattr(similarity_config, "focus_fields", ["prompt", "input", "query", "user", "user_message"]) or [])

    extracted_parts: List[str] = []

    if isinstance(row_data, dict):
        # 1. OpenAI / Anthropic format: {"messages": [{"role": "user", "content": "..."}, ...]}
        messages = row_data.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    role = str(msg.get("role", "")).lower()
                    if role in focus_roles:
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            extracted_parts.append(content)
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    txt = part.get("text")
                                    if isinstance(txt, str) and txt.strip():
                                        extracted_parts.append(txt)

        # 2. Key focus check (e.g. 'prompt', 'input', 'query', 'user')
        if not extracted_parts:
            for k, v in row_data.items():
                if str(k).lower() in focus_fields:
                    if isinstance(v, str) and v.strip():
                        extracted_parts.append(v)

    if extracted_parts:
        return "\n".join(extracted_parts)

    # 3. Fallback: JSON string representation
    if isinstance(row_data, (dict, list)):
        import json
        return json.dumps(row_data, sort_keys=True, ensure_ascii=False)
    return str(row_data)


def normalize_similarity_text(text: str) -> str:
    """Normalize text for shingling (lowercase, strip non-alphanumeric, collapse spaces)."""
    if not text:
        return ""
    lowercased = text.lower()
    # Keep alphanumeric characters and whitespace
    cleaned = re.sub(r"[^\w\s]", " ", lowercased, flags=re.UNICODE)
    collapsed = re.sub(r"\s+", " ", cleaned).strip()
    return collapsed


def extract_shingles(text: str, shingle_size: int = 3) -> Set[str]:
    """Extract character n-grams of specified shingle size."""
    normalized = normalize_similarity_text(text)
    if not normalized:
        return set()
    if len(normalized) <= shingle_size:
        return {normalized}
    shingles = set()
    for i in range(len(normalized) - shingle_size + 1):
        shingles.add(normalized[i : i + shingle_size])
    return shingles


def _generate_hash_parameters(num_hashes: int, seed: int = 42) -> List[Tuple[int, int]]:
    """Generate fixed deterministic linear hash parameters (a, b) for MinHash."""
    rng = random.Random(seed)
    params = []
    for _ in range(num_hashes):
        a = rng.randint(1, MERSENNE_PRIME - 1)
        b = rng.randint(0, MERSENNE_PRIME - 1)
        params.append((a, b))
    return params


def compute_minhash_signature(
    shingles: Set[str],
    num_hashes: int = 64,
    seed: int = 42,
    hash_params: Optional[List[Tuple[int, int]]] = None,
) -> List[int]:
    """Compute MinHash signature vector for a set of shingles."""
    if not shingles:
        return [0] * num_hashes

    if hash_params is None:
        hash_params = _generate_hash_parameters(num_hashes, seed)

    # For long texts, bound shingle sample to max 50 shingles for fast O(1) signature computation
    if len(shingles) > 50:
        shingles_list = [s for i, s in enumerate(shingles) if i < 50]
    else:
        shingles_list = list(shingles)

    shingle_hashes = [hash(s) & 0x7FFFFFFF for s in shingles_list]
    prime = MERSENNE_PRIME

    return [
        min((a * h + b) % prime for h in shingle_hashes)
        for a, b in hash_params
    ]


def compute_exact_jaccard(shingles_a: Set[str], shingles_b: Set[str]) -> float:
    """Compute exact Jaccard similarity between two shingle sets."""
    if not shingles_a and not shingles_b:
        return 1.0
    if not shingles_a or not shingles_b:
        return 0.0
    intersection_len = len(shingles_a.intersection(shingles_b))
    union_len = len(shingles_a.union(shingles_b))
    return intersection_len / union_len if union_len > 0 else 0.0


@dataclass
class SimilarityCandidate:
    """Candidate match pair identified by Similarity Engine."""

    source_id: str
    target_id: str
    source_text: str
    target_text: str
    jaccard_similarity: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "jaccard_similarity": self.jaccard_similarity,
            "metadata": self.metadata,
        }


class SimilarityIndex:
    """Reusable MinHash + LSH Similarity Index."""

    def __init__(
        self,
        shingle_size: int = 3,
        num_hashes: int = 64,
        bands: int = 16,
        threshold: float = 0.85,
        seed: int = 42,
    ):
        self.shingle_size = shingle_size
        self.num_hashes = num_hashes
        self.bands = bands
        self.rows_per_band = max(1, num_hashes // bands)
        self.threshold = threshold
        self.seed = seed

        self.hash_params = _generate_hash_parameters(num_hashes, seed)

        # Storage
        self.items: Dict[str, Dict[str, Any]] = {}
        self.lsh_buckets: Dict[str, Set[str]] = {}

    def add_item(self, item_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Index an item into MinHash LSH structure."""
        if not text:
            return

        shingles = extract_shingles(text, self.shingle_size)
        sig = compute_minhash_signature(shingles, self.num_hashes, self.seed, self.hash_params)

        self.items[item_id] = {
            "id": item_id,
            "text": text,
            "shingles": shingles,
            "signature": sig,
            "metadata": metadata or {},
        }

        # Index signature into LSH bands
        for band_idx in range(self.bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            if start >= len(sig):
                break
            band_tuple = tuple(sig[start:end])
            bucket_key = f"{band_idx}:{hash(band_tuple)}"
            self.lsh_buckets.setdefault(bucket_key, set()).add(item_id)

    def query_item(self, text: str, threshold: Optional[float] = None) -> List[SimilarityCandidate]:
        """Query text against index to find similar items matching or exceeding threshold."""
        t_val = threshold if threshold is not None else self.threshold
        query_shingles = extract_shingles(text, self.shingle_size)
        if not query_shingles:
            return []

        query_sig = compute_minhash_signature(query_shingles, self.num_hashes, self.seed, self.hash_params)

        # Gather candidate IDs from LSH buckets
        candidate_ids: Set[str] = set()
        for band_idx in range(self.bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            if start >= len(query_sig):
                break
            band_tuple = tuple(query_sig[start:end])
            bucket_key = f"{band_idx}:{hash(band_tuple)}"
            candidate_ids.update(self.lsh_buckets.get(bucket_key, set()))

        # Compute exact Jaccard similarity for candidates
        results: List[SimilarityCandidate] = []
        for candidate_id in candidate_ids:
            item = self.items[candidate_id]
            jaccard = compute_exact_jaccard(query_shingles, item["shingles"])
            if jaccard >= t_val:
                results.append(
                    SimilarityCandidate(
                        source_id="query",
                        target_id=candidate_id,
                        source_text=text,
                        target_text=item["text"],
                        jaccard_similarity=jaccard,
                        metadata=item["metadata"],
                    )
                )

        results.sort(key=lambda c: (-c.jaccard_similarity, c.target_id))
        return results

    def find_all_pairs(self, threshold: Optional[float] = None, max_bucket_size: int = 100) -> List[SimilarityCandidate]:
        """Find all near-duplicate item pairs in the index matching or exceeding threshold."""
        t_val = threshold if threshold is not None else self.threshold

        candidate_pairs: Set[Tuple[str, str]] = set()

        for bucket_items in self.lsh_buckets.values():
            if 1 < len(bucket_items) <= max_bucket_size:
                sorted_items = sorted(list(bucket_items))
                for i in range(len(sorted_items)):
                    for j in range(i + 1, len(sorted_items)):
                        candidate_pairs.add((sorted_items[i], sorted_items[j]))

        results: List[SimilarityCandidate] = []
        for id_a, id_b in candidate_pairs:
            item_a = self.items[id_a]
            item_b = self.items[id_b]
            jaccard = compute_exact_jaccard(item_a["shingles"], item_b["shingles"])
            if jaccard >= t_val:
                merged_meta = {"source_metadata": item_a["metadata"], "target_metadata": item_b["metadata"]}
                results.append(
                    SimilarityCandidate(
                        source_id=id_a,
                        target_id=id_b,
                        source_text=item_a["text"],
                        target_text=item_b["text"],
                        jaccard_similarity=jaccard,
                        metadata=merged_meta,
                    )
                )

        results.sort(key=lambda c: (-c.jaccard_similarity, c.source_id, c.target_id))
        return results

    def find_cross_role_pairs(
        self, source_role: str, target_role: str, threshold: Optional[float] = None
    ) -> List[SimilarityCandidate]:
        """Find near-duplicate pairs where source item has source_role and target item has target_role."""
        all_pairs = self.find_all_pairs(threshold)
        cross_pairs: List[SimilarityCandidate] = []

        for cand in all_pairs:
            src_item = self.items.get(cand.source_id, {})
            tgt_item = self.items.get(cand.target_id, {})

            src_roles = set(src_item.get("metadata", {}).get("roles", []))
            tgt_roles = set(tgt_item.get("metadata", {}).get("roles", []))

            if source_role in src_roles and target_role in tgt_roles:
                cross_pairs.append(cand)
            elif target_role in src_roles and source_role in tgt_roles:
                # Flip direction so source is source_role and target is target_role
                cross_pairs.append(
                    SimilarityCandidate(
                        source_id=cand.target_id,
                        target_id=cand.source_id,
                        source_text=cand.target_text,
                        target_text=cand.source_text,
                        jaccard_similarity=cand.jaccard_similarity,
                        metadata={"source_metadata": tgt_item.get("metadata", {}), "target_metadata": src_item.get("metadata", {})},
                    )
                )

        cross_pairs.sort(key=lambda c: (-c.jaccard_similarity, c.source_id, c.target_id))
        return cross_pairs
