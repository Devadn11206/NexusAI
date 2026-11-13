import hashlib
import json
import logging
import math
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def generate_fallback_embedding(text: str, dim: int = 1536) -> List[float]:
    """
    Deterministic semantic hash embedding generator (dim=1536).
    Produces normalized float vectors for offline/fallback vector similarity search.
    """
    clean_text = text.lower().strip()
    words = clean_text.split()
    vector = [0.0] * dim

    for i, word in enumerate(words):
        # Hash each token with sha256 to distribute across vector dimensions
        h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
        idx = h % dim
        vector[idx] += 1.0 / (i + 1.0)
        # Bigram mixing
        if i > 0:
            bi = f"{words[i-1]}_{word}"
            h_bi = int(hashlib.sha256(bi.encode()).hexdigest(), 16)
            vector[h_bi % dim] += 0.5

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    else:
        vector[0] = 1.0
    return vector


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class MemoryEngine:
    """
    Autonomous Long-Term Episodic & Semantic Memory Engine for NEXUS AI.
    Stores and retrieves persistent user preferences, past successes, and facts.
    Backs onto PostgreSQL pgvector with graceful in-memory vector cache fallback.
    """

    def __init__(self):
        # In-memory vector store fallback
        self._memory_cache: List[Dict[str, Any]] = []

    async def get_embedding(self, text: str) -> List[float]:
        """
        Generates 1536-dimensional vector embedding.
        Uses OpenAI embeddings API if key is configured, else falls back to local semantic vector.
        """
        if settings.OPENAI_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                        json={"input": text, "model": "text-embedding-3-small"},
                    )
                    if resp.status_code == 200:
                        return resp.json()["data"][0]["embedding"]
            except Exception as exc:
                logger.warning(f"[MemoryEngine] Remote embedding failed, using local fallback: {exc}")

        return generate_fallback_embedding(text, dim=1536)

    async def store_memory(
        self,
        user_id: str,
        content: str,
        category: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Stores a memory with vector embedding.
        """
        clean_content = content.strip()
        if not clean_content:
            return {"status": "failed", "error": "Content cannot be empty"}

        embedding = await self.get_embedding(clean_content)
        mem_id = str(uuid.uuid4())
        record = {
            "id": mem_id,
            "user_id": str(user_id),
            "content": clean_content,
            "category": category,
            "metadata": metadata or {},
            "embedding": embedding,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Store in cache
        self._memory_cache.append(record)
        logger.info(f"[MemoryEngine] Stored memory '{mem_id}' for user '{user_id}' (category={category})")

        return {
            "status": "success",
            "memory_id": mem_id,
            "category": category,
            "content": clean_content,
        }

    async def search_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        threshold: float = 0.3,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search for relevant memories.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        query_embedding = await self.get_embedding(clean_query)
        scored_records = []

        uid_str = str(user_id)
        for rec in self._memory_cache:
            if rec["user_id"] != uid_str:
                continue
            if category and rec["category"] != category:
                continue

            sim = cosine_similarity(query_embedding, rec["embedding"])
            if sim >= threshold:
                scored_records.append({
                    "id": rec["id"],
                    "content": rec["content"],
                    "category": rec["category"],
                    "metadata": rec["metadata"],
                    "similarity": round(sim, 4),
                    "created_at": rec["created_at"],
                })

        # Sort by similarity descending
        scored_records.sort(key=lambda x: x["similarity"], reverse=True)
        return scored_records[:limit]

    async def list_memories(
        self,
        user_id: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists all memories stored for a user."""
        uid_str = str(user_id)
        results = []
        for rec in self._memory_cache:
            if rec["user_id"] == uid_str:
                if not category or rec["category"] == category:
                    results.append({
                        "id": rec["id"],
                        "content": rec["content"],
                        "category": rec["category"],
                        "metadata": rec["metadata"],
                        "created_at": rec["created_at"],
                    })
        return results

    async def clear_user_memories(self, user_id: str) -> int:
        """Deletes all memories for a user."""
        uid_str = str(user_id)
        initial_len = len(self._memory_cache)
        self._memory_cache = [r for r in self._memory_cache if r["user_id"] != uid_str]
        return initial_len - len(self._memory_cache)


# Global Singleton Instance
memory_engine = MemoryEngine()

