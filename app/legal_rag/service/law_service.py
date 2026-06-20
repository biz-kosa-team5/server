from __future__ import annotations

from ..client import LawApiClient
from ..constants import DAILY_TERMS, LAW_NAMES
from ..dao import LawDao
from ..parser import parse_law, parse_term_mappings


class LawCollectionService:
  def __init__(self, dao: LawDao, client: LawApiClient): self.dao, self.client = dao, client

  def ingest(self, keywords: list[str] | None) -> dict[str, int]:
    names = list(dict.fromkeys(x.strip() for x in (keywords or LAW_NAMES) if x.strip())); success = failed = 0
    for name in names:
      url = None
      try:
        search = self.client.search_laws(name); url = search.request_url
        candidate = self.client.select_current_candidate(search.payload, name)
        mst = str(candidate.get("법령일련번호") or candidate.get("MST") or "")
        if not mst: raise ValueError("Selected law has no MST")
        body = self.client.get_law_body(mst); url = body.request_url
        self.dao.add_raw(source_type="law_api", target="eflaw", query=name, request_url=url,
          response_json=body.payload, status="SUCCESS"); self.dao.commit(); success += 1
      except Exception as error:
        self.dao.rollback(); self.dao.add_raw(source_type="law_api", target="eflaw", query=name,
          request_url=url, status="FAILED", error_message=str(error)[:4000]); self.dao.commit(); failed += 1
    return {"processed": len(names), "succeeded": success, "failed": failed}


class LawParsingService:
  def __init__(self, dao: LawDao): self.dao = dao

  def parse(self, raw_ids: list[int] | None) -> dict[str, int]:
    rows = self.dao.pending_raw(raw_ids); success = failed = saved = 0
    for raw in rows:
      try:
        documents = parse_law(raw.response_json, raw.request_url)
        if not documents: raise ValueError("No eligible articles found")
        for document in documents: self.dao.upsert_document(document)
        raw.status = "PARSED"; raw.error_message = None; self.dao.commit(); success += 1; saved += len(documents)
      except Exception as error:
        self.dao.rollback(); raw = self.dao.session.get(type(raw), raw.id)
        raw.status = "PARSE_FAILED"; raw.error_message = str(error)[:4000]; self.dao.commit(); failed += 1
    return {"processed": len(rows), "succeeded": success, "failed": failed, "documents_saved": saved}


class TermMappingCollectionService:
  def __init__(self, dao: LawDao, client: LawApiClient): self.dao, self.client = dao, client

  def ingest_raw(self, keywords: list[str] | None) -> dict[str, int]:
    terms = list(dict.fromkeys(x.strip() for x in (keywords or DAILY_TERMS) if x.strip()))
    success = failed = 0
    for term in terms:
      url = None
      try:
        response = self.client.get_term_mappings(term); url = response.request_url
        self.dao.add_raw(source_type="term_mapping_api", target="dlytrmRlt", query=term,
          request_url=url, response_json=response.payload, status="SUCCESS")
        self.dao.commit(); success += 1
      except Exception as error:
        self.dao.rollback()
        self.dao.add_raw(source_type="term_mapping_api", target="dlytrmRlt", query=term,
          request_url=url, status="FAILED", error_message=str(error)[:4000])
        self.dao.commit(); failed += 1
    return {"processed": len(terms), "succeeded": success, "failed": failed}


class TermMappingParsingService:
  def __init__(self, dao: LawDao): self.dao = dao

  def parse(self, raw_ids: list[int] | None) -> dict[str, int]:
    rows = self.dao.pending_term_raw(raw_ids); success = failed = saved = 0
    for raw in rows:
      try:
        mappings = parse_term_mappings(raw.response_json)
        for mapping in mappings:
          self.dao.upsert_mapping(mapping.daily_term, mapping.legal_term, mapping.relation_type,
            mapping.priority, mapping.raw_data)
        raw.status = "PARSED" if mappings else "SKIPPED"; raw.error_message = None; self.dao.commit()
        success += 1; saved += len(mappings)
      except Exception as error:
        self.dao.rollback(); raw = self.dao.session.get(type(raw), raw.id)
        raw.status = "PARSE_FAILED"; raw.error_message = str(error)[:4000]; self.dao.commit(); failed += 1
    return {"processed": len(rows), "succeeded": success, "failed": failed, "mappings_saved": saved}
