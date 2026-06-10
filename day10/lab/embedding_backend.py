from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class EmbeddingBackend:
    provider: str
    model: str

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_queries(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class CohereEmbeddingBackend(EmbeddingBackend):
    def __init__(self, *, api_key: str, model: str) -> None:
        super().__init__(provider="cohere", model=model)
        import cohere

        self._client = cohere.Client(api_key)

    def _embed(self, texts: List[str], *, input_type: str) -> List[List[float]]:
        if not texts:
            return []
        res = self._client.embed(
            texts=texts,
            model=self.model,
            input_type=input_type,
            embedding_types=["float"],
        )
        embeddings = getattr(res.embeddings, "float", None)
        if embeddings is None:
            embeddings = res.embeddings
        return [list(v) for v in embeddings]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, input_type="search_document")

    def embed_queries(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, input_type="search_query")


class SentenceTransformerBackend(EmbeddingBackend):
    def __init__(self, *, model: str) -> None:
        super().__init__(provider="sentence_transformers", model=model)
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model)

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_queries(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)


def get_embedding_backend() -> EmbeddingBackend:
    provider = os.environ.get("EMBEDDING_PROVIDER", "").strip().lower()
    if not provider:
        provider = "cohere" if os.environ.get("COHERE_API_KEY") else "sentence_transformers"

    if provider == "cohere":
        api_key = os.environ.get("COHERE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("COHERE_API_KEY is required when EMBEDDING_PROVIDER=cohere.")
        model = os.environ.get("COHERE_EMBEDDING_MODEL", "embed-multilingual-v3.0").strip()
        return CohereEmbeddingBackend(api_key=api_key, model=model)

    if provider in {"sentence_transformers", "sentence-transformers", "local"}:
        model = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
        return SentenceTransformerBackend(model=model)

    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER={provider!r}.")
