from app.chatbot.service.answer import build_answer_observations

from chatbot_answer_helpers import partial_success_context


def test_build_answer_observations_splits_successful_and_failed_fragments():
  context = partial_success_context()

  observations = build_answer_observations(context)

  assert observations["resultShape"] == "multiple"
  assert observations["successfulObservations"] == [context.fragments[0]]
  assert observations["failedObservations"][0]["text"] == context.fragments[1]["text"]
  assert observations["singleResult"] is None
  assert observations["multipleResults"] == context.result
  assert observations["rawResponse"]["status"] == context.status
  assert observations["rawResponse"]["fragments"][0] == {
    "index": context.fragments[0]["index"],
    "text": context.fragments[0]["text"],
    "status": context.fragments[0]["status"],
  }
  assert observations["rawResponse"]["fragments"][1]["text"] == context.fragments[1]["text"]
  assert "result" not in observations["rawResponse"]


def test_build_answer_observations_removes_nested_answers():
  context = partial_success_context()
  context.fragments[0]["result"]["answer"] = "nested answer"
  context.result[0]["answer"] = "nested answer"

  observations = build_answer_observations(context)

  assert "answer" not in observations["successfulObservations"][0]["result"]
  assert "answer" not in observations["multipleResults"][0]
  assert "result" not in observations["rawResponse"]["fragments"][0]
