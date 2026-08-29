import hashlib
import json
import re
import torch
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import settings
from ..models import Document, DocumentChunk


class EmbeddingService:
    """A deterministic PyTorch hashing embedder suitable for a dependency-light MVP.

    Its interface is compatible with replacing the implementation by a sentence transformer.
    """
    def __init__(self, dimensions: int = settings.embedding_dimensions):
        self.dimensions = dimensions
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors = torch.zeros((len(texts), self.dimensions), device=self.device)
        with torch.inference_mode():
            for row, text in enumerate(texts):
                for token in re.findall(r"\w+", text.lower()):
                    index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimensions
                    vectors[row, index] += 1
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            vectors = torch.nan_to_num(vectors)
        return vectors.cpu().tolist()

    def embed(self, text: str) -> list[float]: return self.embed_many([text])[0]


class RetrievalService:
    def __init__(self, embeddings: EmbeddingService): self.embeddings = embeddings

    def search(self, db: Session, user_id: str, query: str, top_k: int):
        query_vector = torch.tensor(self.embeddings.embed(query))
        rows = db.execute(select(DocumentChunk, Document.filename).join(Document).where(DocumentChunk.user_id == user_id, Document.status == "ready")).all()
        scored = []
        for chunk, filename in rows:
            score = float(torch.dot(query_vector, torch.tensor(json.loads(chunk.embedding_json))))
            scored.append((score, chunk, filename))
        return sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]


class LLMService:
    """Safe local fallback. Production implementation calls a configured LLM provider."""
    def answer(self, question: str, sources: list[dict]) -> str:
        if not sources or sources[0]["score"] <= 0:
            return "I couldn't find enough information in your uploaded documents to answer that."
        context = " ".join(source["text"] for source in sources[:2])
        return f"Based on your documents: {context[:900]}"
