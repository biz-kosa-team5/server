PRAGMA foreign_keys = ON;

CREATE TABLE regions (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  parent_id INTEGER REFERENCES regions(id),
  center_lat REAL NOT NULL,
  center_lng REAL NOT NULL,
  unit_cnt_sum INTEGER
);

CREATE TABLE complexes (
  id INTEGER PRIMARY KEY,
  region_id INTEGER NOT NULL REFERENCES regions(id),
  parcel_id INTEGER NOT NULL,
  pnu TEXT,
  name TEXT NOT NULL,
  trade_name TEXT,
  address TEXT,
  latitude REAL,
  longitude REAL,
  dong_cnt INTEGER,
  unit_cnt INTEGER,
  use_date TEXT
);

CREATE TABLE trades (
  id INTEGER PRIMARY KEY,
  complex_id INTEGER NOT NULL REFERENCES complexes(id),
  deal_date TEXT NOT NULL,
  deal_amount INTEGER NOT NULL,
  excl_area REAL NOT NULL,
  floor INTEGER,
  apt_dong TEXT
);

CREATE INDEX idx_regions_code ON regions(code);
CREATE INDEX idx_regions_parent_id ON regions(parent_id);
CREATE INDEX idx_complexes_region_id ON complexes(region_id);
CREATE INDEX idx_complexes_parcel_id ON complexes(parcel_id);
CREATE INDEX idx_complexes_name ON complexes(name);
CREATE INDEX idx_complexes_coordinate ON complexes(latitude, longitude);
CREATE INDEX idx_trades_complex_date ON trades(complex_id, deal_date);
CREATE INDEX idx_trades_amount ON trades(deal_amount);
CREATE INDEX idx_trades_area ON trades(excl_area);
