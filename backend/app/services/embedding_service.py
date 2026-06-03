from __future__ import annotations

import hashlib
import math
import re
from collections import Counter


class HashEmbeddingService:
    """Deterministic lightweight embedding used in MVP/local dev.

    This is pgvector-ready: the returned list can later be replaced by a real local
    embedding model and stored in pgvector/Qdrant without changing the duplicate
    detection interface.
    """

    def __init__(self, dimensions: int = 128):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[\wÀ-ỹ]+", (text or "").lower())
        vector = [0.0] * self.dimensions
        counts = Counter(tokens)
        for token, count in counts.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1 if digest[4] % 2 == 0 else -1
            vector[index] += sign * (1 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [round(v / norm, 6) for v in vector]

    def cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        n = min(len(left), len(right))
        return sum(left[i] * right[i] for i in range(n))
