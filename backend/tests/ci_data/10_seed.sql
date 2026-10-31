-- Deterministic, synthetic CI fixture. NOT production data.
-- Sixteen jurisdictions, 60 months of ledger + NAICS data ending last month.
-- Amounts follow a fixed formula (base * seasonal factor * growth), so
-- assertions on ordering (Oklahoma City is the top city) are stable.

INSERT INTO jurisdictions (copo, name, jurisdiction_type, county_name, population, tax_rate_sales, tax_rate_use) VALUES
 ('5521','Oklahoma City','city','Oklahoma',681054,0.0450,0.0450),
 ('7210','Tulsa','city','Tulsa',413066,0.0402,0.0402),
 ('0955','Yukon','city','Canadian',25405,0.0400,0.0400),
 ('4508','Broken Bow','city','McCurtain',4120,0.0400,0.0400),
 ('2501','Edmond','city','Oklahoma',94428,0.0400,0.0400),
 ('0188','Adair County','county','Adair',19495,0.0100,0.0100);

-- Ten more small synthetic cities so list/pagination/top-10 assertions have rows.
INSERT INTO jurisdictions (copo, name, jurisdiction_type, county_name, population, tax_rate_sales, tax_rate_use)
SELECT lpad((9000 + n)::text, 4, '0'), 'Testville ' || n, 'city', 'Test', 1000 + n, 0.0300, 0.0300
FROM generate_series(1, 10) AS n;

-- 120 synthetic NAICS codes so per-city industry lists look production-like.
INSERT INTO naics_codes (activity_code, description, sector_description)
SELECT (441000 + n)::text, 'Synthetic Industry ' || n, 'Retail Trade' FROM generate_series(1, 120) AS n;

INSERT INTO naics_codes (activity_code, description, sector_description) VALUES
 ('455110','Department Stores','Retail Trade'),
 ('445110','Supermarkets and Grocery Stores','Retail Trade'),
 ('722511','Full-Service Restaurants','Accommodation and Food Services'),
 ('221122','Electric Power Distribution','Utilities'),
 ('236220','Commercial Building Construction','Construction'),
 ('423110','Automobile Merchant Wholesalers','Wholesale Trade');

INSERT INTO naics_sectors (sector, sector_name) VALUES
 ('45','Retail Trade'),('44','Retail Trade'),('72','Accommodation and Food Services'),
 ('22','Utilities'),('23','Construction'),('42','Wholesale Trade');

-- 60 monthly periods ending last month; m = months back from the latest.
CREATE TEMP TABLE _months AS
SELECT (date_trunc('month', current_date) - make_interval(months => m))::date AS d, 60 - m AS idx
FROM generate_series(1, 60) AS m;

CREATE TEMP TABLE _base (copo text, base numeric);
INSERT INTO _base VALUES ('5521',9000000),('7210',6000000),('2501',2000000),('0955',500000),('4508',90000),('0188',60000);
INSERT INTO _base SELECT lpad((9000 + n)::text, 4, '0'), 20000 + n * 1000 FROM generate_series(1, 10) AS n;

INSERT INTO ledger_records (copo, tax_type, voucher_date, tax_rate, current_month_collection, returned)
SELECT b.copo, t.tt::tax_type, m.d,
       CASE WHEN b.copo='0188' THEN 0.0100 ELSE 0.0400 END,
       ROUND(b.base * (CASE t.tt WHEN 'sales' THEN 1 ELSE 0.15 END) * (1 + (m.idx % 12) / 40.0 + m.idx / 400.0), 2),
       ROUND(b.base * (CASE t.tt WHEN 'sales' THEN 1 ELSE 0.15 END) * (1 + (m.idx % 12) / 40.0 + m.idx / 400.0), 2)
FROM _base b CROSS JOIN _months m CROSS JOIN (VALUES ('sales'),('use')) AS t(tt);

INSERT INTO naics_records (copo, tax_type, report_date, activity_code, activity_code_description, tax_rate, sector_total, year_to_date)
SELECT b.copo, t.tt::tax_type, m.d, c.code, (SELECT description FROM naics_codes WHERE activity_code = c.code), 0.0400,
       ROUND(b.base * c.share * (CASE t.tt WHEN 'sales' THEN 1 ELSE 0.15 END) * (1 + (m.idx % 12) / 40.0), 2),
       ROUND(b.base * c.share * (CASE t.tt WHEN 'sales' THEN 1 ELSE 0.15 END) * (1 + (m.idx % 12) / 40.0) * EXTRACT(MONTH FROM m.d), 2)
FROM _base b CROSS JOIN _months m
CROSS JOIN (VALUES ('sales'),('use')) AS t(tt)
CROSS JOIN (VALUES ('455110',0.30),('445110',0.25),('722511',0.20),('221122',0.10),('236220',0.10),('423110',0.05)) AS c(code, share);

INSERT INTO anomalies (copo, tax_type, anomaly_date, anomaly_type, severity, expected_value, actual_value, description)
SELECT '0955','sales', (date_trunc('month', current_date) - interval '2 months')::date, v.t::anomaly_type, v.s::anomaly_severity, 500000, v.a, 'Synthetic CI anomaly'
FROM (VALUES ('yoy_spike','high',900000),('yoy_drop','critical',100000),('mom_outlier','medium',750000),('naics_shift','low',620000)) AS v(t,s,a);

-- Yukon: 120 extra NAICS activities for the latest 3 months.
INSERT INTO naics_records (copo, tax_type, report_date, activity_code, activity_code_description, tax_rate, sector_total, year_to_date)
SELECT '0955','sales', m.d, c.activity_code, c.description, 0.0400, 1000 + (ascii(right(c.activity_code,1)) * 7) + m.idx, 5000
FROM _months m JOIN naics_codes c ON c.activity_code BETWEEN '441001' AND '441120'
WHERE m.idx > 57;

REFRESH MATERIALIZED VIEW mv_monthly_revenue_by_city;
REFRESH MATERIALIZED VIEW mv_top_naics_by_city;
REFRESH MATERIALIZED VIEW mv_yoy_comparison;
