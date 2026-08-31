from app.services.retrieval import RetrievalService


def test_query_expansion_connects_school_questions_to_education_terms():
    terms = RetrievalService.query_terms("What school did he go to?")
    assert {"school", "education", "university", "college"} <= terms
