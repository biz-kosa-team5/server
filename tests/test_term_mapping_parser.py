from app.chatbot.features.legal_contract.rag.parser import parse_term_mappings


def test_parse_term_mappings_normalizes_relation():
  payload = {"dlytrmRltService": {"키워드": "집", "일상용어": {
    "일상용어명": "집", "연계용어": [{
      "id": "1", "용어관계": "동의어", "법령용어명": "주택", "용어관계코드": "140301", "비고": "",
    }],
  }}}
  mappings = parse_term_mappings(payload)
  assert len(mappings) == 1
  assert mappings[0].daily_term == "집"
  assert mappings[0].legal_term == "주택"
  assert mappings[0].relation_type == "SYNONYM"
  assert mappings[0].priority == 100
