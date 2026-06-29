TRUNCATE TABLE trades, complexes, regions, pois RESTART IDENTITY;

COPY regions (id, code, name, type, parent_id, center_lat, center_lng, unit_cnt_sum)
FROM '/import/regions.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY complexes (
  id, region_id, parcel_id, pnu, name, trade_name, address,
  latitude, longitude, dong_cnt, unit_cnt, use_date
)
FROM '/import/complexes.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY trades (id, complex_id, deal_date, deal_amount, excl_area, floor, apt_dong)
FROM '/import/trades.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY pois (category, name, subtype, latitude, longitude)
FROM '/import/pois.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

CREATE TEMP TABLE lifestyle_pois_import (
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  subtype TEXT NOT NULL,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL
);

COPY lifestyle_pois_import (category, name, subtype, latitude, longitude)
FROM '/import/large_marts.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY lifestyle_pois_import (category, name, subtype, latitude, longitude)
FROM '/import/hospitals.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

INSERT INTO pois (category, name, subtype, latitude, longitude)
SELECT
  CASE category
    WHEN 'large_mart' THEN 'commercial'
    WHEN 'hospital' THEN 'medical'
    ELSE category
  END,
  name,
  subtype,
  latitude,
  longitude
FROM lifestyle_pois_import;

TRUNCATE TABLE law_documents, daily_legal_term_mappings, raw_api_responses RESTART IDENTITY;

COPY daily_legal_term_mappings (
  id, daily_term, legal_term, relation_type, domain, priority, raw_data, created_at, updated_at
)
FROM '/import/daily_legal_term_mappings.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY raw_api_responses (
  id, source_type, target, query, request_url, response_json, status, error_message, collected_at
)
FROM '/import/raw_api_responses.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

COPY law_documents (
  id, parent_document_id, law_id, mst, law_name, law_type, ministry,
  article_no, article_title, paragraph_no, doc_type, content, metadata,
  source_url, effective_date, parse_status, parse_error, embedding,
  embedding_model, embedding_status, embedding_error, embedding_content_hash,
  embedded_at, collected_at, updated_at
)
FROM '/import/law_documents.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

SELECT setval(pg_get_serial_sequence('daily_legal_term_mappings', 'id'), COALESCE(MAX(id), 1), true)
FROM daily_legal_term_mappings;

SELECT setval(pg_get_serial_sequence('raw_api_responses', 'id'), COALESCE(MAX(id), 1), true)
FROM raw_api_responses;

SELECT setval(pg_get_serial_sequence('law_documents', 'id'), COALESCE(MAX(id), 1), true)
FROM law_documents;

ANALYZE daily_legal_term_mappings;
ANALYZE raw_api_responses;
ANALYZE law_documents;
