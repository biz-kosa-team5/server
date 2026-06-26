from __future__ import annotations

from typing import Any

from .common import clean_text, dict_value, list_value


def format_legal_contract_result(result: dict[str, Any]) -> str:
  answer = clean_text(result.get("answer"))
  if answer:
    return answer

  summary = clean_text(result.get("summary"))
  if summary:
    return summary

  sources = [dict_value(item) for item in list_value(result.get("sources"))[:3]]
  references = []
  for source in sources:
    law_name = clean_text(source.get("lawName"))
    article_no = clean_text(source.get("articleNo"))
    if law_name and article_no:
      references.append(f"{law_name} {article_no}")
    elif law_name:
      references.append(law_name)
  if references:
    return "관련 법령 근거를 조회했습니다. 근거 조문은 " + ", ".join(references) + "입니다."
  return clean_text(result.get("message"))
