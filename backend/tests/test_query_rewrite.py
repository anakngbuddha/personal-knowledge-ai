from app.llm.prompts import SYSTEM_PROMPT_EXPERT, SYSTEM_PROMPT_STRICT
from app.llm.fake import FakeLLMProvider
from app.retrieval.rewrite import expand_queries, rewrite_query


def test_followup_is_rewritten_with_prior_question():
    history = [{"role": "user", "content": "Tell me about the Jabra Speak 750"}]
    assert "Jabra" in rewrite_query("what about the pricing?", history)


def test_standalone_question_is_unchanged():
    assert rewrite_query("How does Poly Studio X50 connect to Teams?") == (
        "How does Poly Studio X50 connect to Teams?"
    )


def test_compare_questions_stay_one_query():
    queries = expand_queries("Compare Jabra and Shure ceiling mics")
    assert queries == ["Compare Jabra and Shure ceiling mics"]


def test_rewrite_does_not_call_the_model(monkeypatch):
    def _boom():
        raise AssertionError("rewrite must not call the model")

    monkeypatch.setattr("app.llm.factory.get_llm_provider", _boom)
    history = [{"role": "user", "content": "Tell me about the Jabra Speak 750"}]
    assert "Jabra" in rewrite_query("what about the pricing?", history)


def test_fake_llm_expert_mode_answers_without_sources():
    provider = FakeLLMProvider()
    answer = provider.generate_grounded_answer(
        "What is a huddle room?",
        [],
        system_prompt=SYSTEM_PROMPT_EXPERT,
    )
    assert answer.refused is False
    assert "general product knowledge" in answer.text.lower()


def test_fake_llm_strict_mode_still_refuses_without_sources():
    provider = FakeLLMProvider()
    answer = provider.generate_grounded_answer(
        "What is a huddle room?",
        [],
        system_prompt=SYSTEM_PROMPT_STRICT,
    )
    assert answer.refused is True
