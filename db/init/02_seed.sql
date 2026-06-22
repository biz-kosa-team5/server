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
