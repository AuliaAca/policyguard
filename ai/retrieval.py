"""Retrieval: memilih pasal kebijakan yang paling relevan untuk sebuah listing.

Indeks disimpan di memori (numpy), bukan di vector database (ADR-012): jumlah pasal
hanya belasan, jadi mencari di memori lebih sederhana dan cukup cepat.

Dua mode:
- "topk": ambil k pasal paling mirip (RAG).
- "all" : kirim semua pasal ke LLM (baseline pembanding).
"""
import logging
import threading
from typing import Protocol

import numpy as np

from ai.types import Listing, PolicyChunk

log = logging.getLogger(__name__)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Mengembalikan matriks (len(texts), dimensi)."""
        ...


class OpenAIEmbedder:
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    def embed(self, texts: list[str]) -> np.ndarray:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return np.array([d.embedding for d in resp.data], dtype=np.float32)


class LocalEmbedder:
    """Model sentence-transformers yang berjalan di mesin sendiri (opsional, lihat requirements-local.txt)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # import di sini: dependensi opsional
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts), dtype=np.float32)


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


def query_text(listing: Listing) -> str:
    return f"{listing.title}\n{listing.description}\nKategori: {listing.category}"


class PolicyRetriever:
    def __init__(self, chunks: list[PolicyChunk], embedder: Embedder | None, top_k: int = 5,
                 mode: str = "topk"):
        if mode not in ("topk", "all"):
            raise ValueError(f"mode retrieval tidak dikenal: {mode}")
        if mode == "topk" and embedder is None:
            raise ValueError("mode topk membutuhkan embedder")
        self.chunks = chunks
        self.mode = mode
        self.top_k = min(top_k, len(chunks))
        self._embedder = embedder
        self._matrix: np.ndarray | None = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.mode == "all" or self._matrix is not None

    def ensure_index(self) -> None:
        """Membangun indeks sekali. Jika gagal (misalnya API embedding mati), dicoba lagi
        pada request berikutnya, sehingga service pulih sendiri tanpa restart."""
        if self.ready:
            return
        with self._lock:
            if self._matrix is None:
                self._matrix = _unit(self._embedder.embed([c.text for c in self.chunks]))
                log.info("indeks kebijakan dibangun", extra={"chunks": len(self.chunks)})

    def retrieve(self, listing: Listing) -> list[tuple[PolicyChunk, float | None]]:
        if self.mode == "all":
            return [(c, None) for c in self.chunks]
        self.ensure_index()
        q = _unit(self._embedder.embed([query_text(listing)]))[0]
        scores = self._matrix @ q                      # cosine similarity, karena semua vektor sudah unit
        top = np.argsort(-scores)[: self.top_k]
        return [(self.chunks[i], float(scores[i])) for i in top]
