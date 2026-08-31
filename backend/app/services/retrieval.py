import hashlib
import json
import re
import torch
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import settings
from ..models import Document, DocumentChunk


class EmbeddingService:
    """Sentence-transformer embeddings with a deterministic offline fallback.

    The default model is a compact semantic encoder. Set
    ``CLOUDMIND_EMBEDDING_PROVIDER=hashing`` for offline development or tests.
    """
    def __init__(
        self,
        dimensions: int = settings.embedding_dimensions,
        provider: str = settings.embedding_provider,
        model_name: str = settings.embedding_model,
    ):
        self.provider = provider.lower()
        if self.provider not in {"semantic", "hashing"}:
            raise ValueError("embedding_provider must be 'semantic' or 'hashing'")
        self.model_name = model_name
        self.dimensions = dimensions if self.provider == "hashing" else settings.semantic_embedding_dimensions
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None

    def _semantic_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - deployment configuration guard
                raise RuntimeError("Install sentence-transformers to use semantic embeddings") from exc
            self._model = SentenceTransformer(self.model_name, device=self.device.type)
            self.dimensions = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.provider == "semantic":
            vectors = self._semantic_model().encode(
                texts,
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return vectors.tolist()
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

    _QUERY_EXPANSIONS = {
        "school": {"education", "university", "college"},
        "intern": {"internship", "experience", "employer", "company"},
        "work": {"experience", "employer", "company", "role"},
    }

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        terms = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
        for term in tuple(terms):
            if term.endswith("ed"):
                terms.add(term[:-2])
            if term.endswith("ing"):
                terms.add(term[:-3])
        return terms

    @classmethod
    def query_terms(cls, query: str) -> set[str]:
        terms = cls._terms(query)
        for term in tuple(terms):
            terms.update(cls._QUERY_EXPANSIONS.get(term, set()))
        return terms

    def _refresh_legacy_embeddings(self, db: Session, user_id: str, dimensions: int) -> None:
        """Upgrade old hashing vectors in place after the semantic-model rollout."""
        chunks = db.scalars(
            select(DocumentChunk)
            .join(Document)
            .where(DocumentChunk.user_id == user_id, Document.status == "ready")
        ).all()
        stale = []
        for chunk in chunks:
            try:
                stale_vector = json.loads(chunk.embedding_json)
            except json.JSONDecodeError:
                stale_vector = []
            if len(stale_vector) != dimensions:
                stale.append(chunk)
        if not stale:
            return
        for chunk, vector in zip(stale, self.embeddings.embed_many([chunk.text for chunk in stale])):
            chunk.embedding_json = json.dumps(vector)
        db.commit()

    def search(self, db: Session, user_id: str, query: str, top_k: int):
        query_vector = torch.tensor(self.embeddings.embed(query))
        self._refresh_legacy_embeddings(db, user_id, len(query_vector))
        query_terms = self.query_terms(query)
        rows = db.execute(select(DocumentChunk, Document.filename).join(Document).where(DocumentChunk.user_id == user_id, Document.status == "ready")).all()
        scored = []
        for chunk, filename in rows:
            vector_score = max(0.0, float(torch.dot(query_vector, torch.tensor(json.loads(chunk.embedding_json)))))
            chunk_terms = self._terms(chunk.text)
            lexical_score = len(query_terms & chunk_terms) / max(1, len(query_terms))
            # Semantic similarity drives meaning; lexical matching preserves exact résumé entities.
            score = 0.85 * vector_score + 0.15 * lexical_score
            scored.append((score, chunk, filename))
        return sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]


class LLMService:
    """Grounded local answer extractor. Production can replace this with an LLM provider."""
    _STOP_WORDS = {"a", "an", "at", "did", "do", "does", "for", "he", "her", "his", "i", "in", "is", "of", "she", "the", "they", "to", "was", "what", "where", "who", "with", "you", "your"}
    _MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    _QUERY_EXPANSIONS = RetrievalService._QUERY_EXPANSIONS

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

    def _query_terms(self, text: str) -> set[str]:
        terms = self._terms(text)
        for term in tuple(terms):
            terms.update(self._QUERY_EXPANSIONS.get(term, set()))
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

    @staticmethod
    def _schools(context: str) -> list[str]:
        institutions = []
        patterns = [
            r"\bUniversity of [A-Z][A-Za-z ,]+?(?=\s+(?:Expected|Bachelor|Master|Associate)|[•\n]|$)",
            r"\b(?:[A-Z][a-z]+\s+){0,2}College\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, context):
                school = re.sub(r"\s+", " ", match.group(0)).strip(" ,")
                if school and school not in institutions:
                    institutions.append(school)
        return institutions

    def answer(self, question: str, sources: list[dict]) -> str:
        if not sources or sources[0]["score"] <= 0:
            return "I couldn't find enough information in your uploaded documents to answer that."
        query_terms = self._query_terms(question)
        context = " ".join(source["text"] for source in sources)
        if {"school", "education", "university", "college"} & query_terms:
            schools = self._schools(context)
            if schools:
                return f"According to the uploaded documents, they attended {' and '.join(schools)}."
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
