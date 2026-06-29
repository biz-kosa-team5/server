from dataclasses import replace

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


def test_build_answer_observations_includes_ui_summary_without_actions():
  context = replace(
    partial_success_context(),
    uiActions=[
      {
        "type": "focus_map",
        "target": {
          "latitude": 37.5124,
          "longitude": 127.0821,
        },
      }
    ],
    uiSummary={
      "hasMapFocus": True,
      "primaryTargetName": "잠실엘스",
      "primaryActionLabel": "잠실엘스 지도 보기",
      "artifactTypes": ["trend_line_chart"],
    },
    uiArtifacts=[
      {
        "type": "trend_line_chart",
        "title": "잠실엘스 시세 흐름",
        "points": [
          {"period": "2025-01", "value": 100000},
          {"period": "2025-02", "value": 110000},
        ],
      }
    ],
  )

  observations = build_answer_observations(context)

  assert observations["uiSummary"]["hasMapFocus"] is True
  assert observations["uiSummary"]["primaryTargetName"] == "잠실엘스"
  assert observations["uiArtifacts"] == [
    {
      "type": "trend_line_chart",
      "title": "잠실엘스 시세 흐름",
      "pointCount": 2,
    }
  ]
  assert "uiActions" not in observations
  assert "latitude" not in str(observations)
  assert "longitude" not in str(observations)
