from app.services.retrieval import LLMService


def test_local_answer_extractor_returns_the_internship_company_not_the_full_resume():
    sources = [{"score": 0.4, "text": "Noah Rai | Education • AI/ML Engineer Intern Jun. 2025 – Oct. 2025 IBM | Remote • Built end-to-end RAG pipelines."}]
    assert LLMService().answer("Where did he intern at?", sources) == "They interned at IBM (Remote)."


def test_local_answer_extractor_declines_when_the_sources_do_not_support_the_question():
    sources = [{"score": 0.4, "text": "L1 regularization uses absolute values for weights."}]
    assert "couldn't find enough" in LLMService().answer("Where did he intern?", sources)
