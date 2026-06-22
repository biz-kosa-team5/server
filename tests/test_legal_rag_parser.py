from app.chatbot.features.legal_contract.rag.parser import parse_law


def test_parse_law_skips_deleted_articles():
  payload = {"Law": {"basicinfo": {"lawId": "L1", "MST": "1", "lawName": "Test Act",
    "lawType": "Act", "ministry": "MOJ", "effectiveDate": "20260618"}, "articles": [
    {"articleNo": "1", "articleTitle": "Purpose", "articleText": "Valid content"},
    {"articleNo": "2", "articleTitle": "Deleted", "articleText": "삭제"}]}}
  documents = parse_law(payload, "https://example.test")
  assert len(documents) == 1
  assert documents[0].content == "Valid content"


def test_parse_law_requires_metadata():
  try:
    parse_law({"Law": {}}, None)
    assert False, "Expected ValueError"
  except ValueError as error:
    assert "metadata" in str(error)


def test_parse_law_handles_branch_number_and_structured_metadata():
  payload = {"법령": {"기본정보": {"법령ID": "L2", "법령명_한글": "테스트법",
    "법종구분": {"content": "법률"}, "소관부처": {"content": "법무부"}, "시행일자": "20260618"},
    "조문": {"조문단위": [{"조문번호": "14", "조문가지번호": "2", "조문여부": "조문",
      "조문제목": "특정 조문", "조문내용": "제14조의2(특정 조문)",
      "항": [{"항번호": "①", "항내용": "첫 번째 항"}, {"항번호": "②", "항내용": "두 번째 항"}]}]}}}
  documents = parse_law(payload, "https://example.test?MST=12345")
  assert len(documents) == 1
  assert documents[0].article_no == "제14조의2"
  assert documents[0].content == "제14조의2(특정 조문) 첫 번째 항 두 번째 항"
  assert documents[0].law_type == "법률"
  assert documents[0].ministry == "법무부"
  assert documents[0].mst == "12345"
