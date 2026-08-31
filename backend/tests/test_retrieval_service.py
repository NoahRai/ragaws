from app.services.retrieval import EmbeddingService, RetrievalService


def test_query_expansion_connects_school_questions_to_education_terms():
    terms = RetrievalService.query_terms("What school did he go to?")
    assert {"school", "education", "university", "college"} <= terms


def test_hashing_provider_remains_available_for_offline_test_runs():
    vectors = EmbeddingService(dimensions=8, provider="hashing").embed_many(["semantic search", ""])
    assert len(vectors) == 2
    assert all(len(vector) == 8 for vector in vectors)
