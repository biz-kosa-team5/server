CREATE TABLE IF NOT EXISTS regions (
  id BIGINT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  parent_id BIGINT REFERENCES regions(id),
  center_lat DOUBLE PRECISION NOT NULL,
  center_lng DOUBLE PRECISION NOT NULL,
  unit_cnt_sum BIGINT
);

CREATE TABLE IF NOT EXISTS complexes (
  id BIGINT PRIMARY KEY,
  region_id BIGINT NOT NULL REFERENCES regions(id),
  parcel_id BIGINT NOT NULL,
  pnu TEXT,
  name TEXT NOT NULL,
  trade_name TEXT,
  address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  dong_cnt INTEGER,
  unit_cnt INTEGER,
  use_date TEXT
);

CREATE TABLE IF NOT EXISTS trades (
  id BIGINT PRIMARY KEY,
  complex_id BIGINT NOT NULL REFERENCES complexes(id),
  deal_date TEXT NOT NULL,
  deal_amount BIGINT NOT NULL,
  excl_area DOUBLE PRECISION NOT NULL,
  floor INTEGER,
  apt_dong TEXT
);

CREATE TABLE IF NOT EXISTS pois (
  id BIGSERIAL PRIMARY KEY,
  category TEXT NOT NULL CHECK (category IN ('station', 'education')),
  name TEXT NOT NULL,
  subtype TEXT NOT NULL,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_regions_code ON regions(code);
CREATE INDEX IF NOT EXISTS idx_regions_parent_id ON regions(parent_id);
CREATE INDEX IF NOT EXISTS idx_complexes_region_id ON complexes(region_id);
CREATE INDEX IF NOT EXISTS idx_complexes_parcel_id ON complexes(parcel_id);
CREATE INDEX IF NOT EXISTS idx_complexes_name ON complexes(name);
CREATE INDEX IF NOT EXISTS idx_complexes_coordinate ON complexes(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_trades_complex_date ON trades(complex_id, deal_date);
CREATE INDEX IF NOT EXISTS idx_trades_amount ON trades(deal_amount);
CREATE INDEX IF NOT EXISTS idx_trades_area ON trades(excl_area);

CREATE TABLE IF NOT EXISTS raw_api_responses (
  id BIGSERIAL PRIMARY KEY, source_type VARCHAR(50) NOT NULL, target VARCHAR(50), query VARCHAR(255),
  request_url TEXT, response_json JSONB, status VARCHAR(50), error_message TEXT, collected_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS law_documents (
  id BIGSERIAL PRIMARY KEY, parent_document_id BIGINT REFERENCES law_documents(id),
  law_id VARCHAR(50) NOT NULL, mst VARCHAR(50), law_name VARCHAR(255) NOT NULL,
  law_type VARCHAR(50), ministry VARCHAR(100), article_no VARCHAR(50) NOT NULL, article_title VARCHAR(255),
  paragraph_no VARCHAR(50) NOT NULL DEFAULT '', doc_type VARCHAR(50) NOT NULL, content TEXT NOT NULL,
  metadata JSONB, source_url TEXT, effective_date DATE NOT NULL, parse_status VARCHAR(30) DEFAULT 'PARSED',
  parse_error TEXT, collected_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_law_documents_article UNIQUE (law_id, effective_date, article_no, paragraph_no)
);

CREATE TABLE IF NOT EXISTS daily_legal_term_mappings (
  id BIGSERIAL PRIMARY KEY, daily_term VARCHAR(255) NOT NULL, legal_term VARCHAR(255) NOT NULL,
  relation_type VARCHAR(50) NOT NULL DEFAULT 'RELATED', domain VARCHAR(100), priority INT DEFAULT 0,
  raw_data JSONB, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_daily_legal_term_mapping UNIQUE (daily_term, legal_term, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_raw_api_responses_target ON raw_api_responses(target);
CREATE INDEX IF NOT EXISTS idx_raw_api_responses_query ON raw_api_responses(query);
CREATE INDEX IF NOT EXISTS idx_law_documents_law_name ON law_documents(law_name);
CREATE INDEX IF NOT EXISTS idx_law_documents_effective_date ON law_documents(effective_date);
CREATE INDEX IF NOT EXISTS idx_law_documents_article_no ON law_documents(article_no);
CREATE INDEX IF NOT EXISTS idx_law_documents_parent_document_id ON law_documents(parent_document_id);
CREATE INDEX IF NOT EXISTS idx_law_documents_metadata ON law_documents USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_daily_legal_term ON daily_legal_term_mappings(daily_term);
CREATE INDEX IF NOT EXISTS idx_daily_legal_term_priority ON daily_legal_term_mappings(priority);
