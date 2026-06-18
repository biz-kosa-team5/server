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
CREATE INDEX IF NOT EXISTS idx_pois_category_subtype ON pois(category, subtype);
CREATE INDEX IF NOT EXISTS idx_pois_name ON pois(name);
CREATE INDEX IF NOT EXISTS idx_pois_location ON pois(latitude, longitude);
