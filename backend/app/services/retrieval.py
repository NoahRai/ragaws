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
    """Grounded local answer extractor. Production can replace this with an LLM provider."""
    _STOP_WORDS = {"a", "an", "at", "did", "do", "does", "for", "he", "her", "his", "i", "in", "is", "of", "she", "the", "they", "to", "was", "what", "where", "who", "with", "you", "your"}
    _MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        terms = set()
        for token in re.findall(r"[a-zA-Z]{3,}", text.lower()):
            if token in cls._STOP_WORDS:
                continue
            terms.add(token)
            if token.endswith("ed"):
                terms.add(token[:-2])
            if token.endswith("ing"):
                terms.add(token[:-3])
        return terms

    @staticmethod
    def _statements(sources: list[dict]) -> list[str]:
        statements = []
        for source in sources:
            # Résumés and technical notes commonly use bullets; preserve each bullet as evidence.
            statements.extend(piece.strip(" .") for piece in re.split(r"[•\n]+", source["text"]) if piece.strip())
        return statements

    def _internship_answer(self, statement: str) -> str | None:
        date_range = rf"{self._MONTH}\.?\s+\d{{4}}\s*(?:–|-|to)\s*{self._MONTH}\.?\s+\d{{4}}\s+"
        match = re.search(date_range + r"(?P<company>[^|.]+?)(?:\s*\|\s*(?P<location>[^.]+))?$", statement, re.IGNORECASE)
        if not match:
            return None
        company = match.group("company").strip()
        location = (match.group("location") or "").strip()
        if not company:
            return None
        location_text = f" ({location})" if location else ""
        return f"They interned at {company}{location_text}."

    def answer(self, question: str, sources: list[dict]) -> str:
        if not sources or sources[0]["score"] <= 0:
            return "I couldn't find enough information in your uploaded documents to answer that."
        query_terms = self._terms(question)
        candidates = self._statements(sources)
        ranked = sorted(candidates, key=lambda statement: len(query_terms & self._terms(statement)), reverse=True)
        if not ranked or not (query_terms & self._terms(ranked[0])):
            return "I couldn't find enough information in your uploaded documents to answer that."
        best = ranked[0]
        if "intern" in query_terms and any(term in question.lower() for term in ("where", "company", "intern")):
            internship = self._internship_answer(best)
            if internship:
                return internship
        return f"According to your documents: {best}."
