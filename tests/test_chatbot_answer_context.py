from app.chatbot.service.answer_context import build_llm_context

from chatbot_answer_helpers import partial_success_context


def test_build_llm_context_splits_successful_and_failed_fragments():
  context = partial_success_context()

  llm_context = build_llm_context(context)

  assert llm_context["resultShape"] == "multiple"
  assert llm_context["successfulFragments"] == [context.fragments[0]]
  assert llm_context["failedFragments"] == [context.fragments[1]]
  assert llm_context["singleResult"] is None
  assert llm_context["multipleResults"] == context.result
  assert llm_context["rawResponse"] == context.to_dict()
