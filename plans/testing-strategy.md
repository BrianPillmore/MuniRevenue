# MuniRev Testing Strategy

## Test Pyramid

```
         ╱╲
        ╱  ╲         Integration (tests/integration/)
       ╱    ╲        Full pipeline: parse -> analyze -> verify
      ╱──────╲
     ╱        ╲       API Tests (backend/tests/test_api_*.py)
    ╱          ╲      FastAPI TestClient against endpoints
   ╱────────────╲
  ╱              ╲     Unit Tests (backend/tests/test_*.py)
 ╱                ╲    Parser, analysis engine, services
╱──────────────────╲
```

## Current Coverage (36 tests, all passing)

### Unit Tests — `backend/tests/`

| File | Tests | What it covers |
|---|---|---|
| `test_analysis.py` | 2 | `canonicalize_tax_data`, `build_analysis` with sample xlsx |
| `test_oktap_parser.py` | 18 | Report type detection, ledger parsing (9 records, values, dates, totals exclusion), NAICS parsing (471 records, sectors, unclassified, decimal precision) |

### API Tests — `backend/tests/test_api_oktap.py`

| Tests | What it covers |
|---|---|
| 16 | Health endpoint, report types, ledger import (success + invalid type + wrong ext + bad xml), NAICS import (success + missing year + invalid month), auto-detect (ledger + naics needs year/month + naics with year/month), bulk import, analyze endpoint (success + reject non-xlsx), report endpoint (HTML output) |

### Integration Tests — `tests/integration/`

| File | Tests | What it covers |
|---|---|---|
| `test_full_pipeline.py` | 3 | Ledger parse + financial total verification, NAICS parse + industry verification, full analysis pipeline from sample xlsx |

## Test Fixtures

Real OkTAP exports stored in `backend/tests/fixtures/`:
- `ledger_yukon_sales_2026.xls` — 9 months of Yukon sales tax ledger data
- `naics_yukon_sales_2026_02.xls` — 471 NAICS industry records for Yukon, Feb 2026

Plus existing sample data in `backend/assets/`:
- `sample-data.xlsx` — 86 months of historical revenue data

## Planned Tests (Phase 1-2)

### Database Tests (requires PostgreSQL)
- [ ] Upsert ledger records (insert + re-import same data)
- [ ] Upsert NAICS records with ON CONFLICT
- [ ] Auto-create jurisdiction on unknown copo
- [ ] Data retrieval API with date range filters
- [ ] Materialized view refresh after import

### Anomaly Detection Tests
- [ ] Z-score spike detection with synthetic data
- [ ] Missing month detection
- [ ] NAICS composition shift detection
- [ ] YoY deviation flagging

### Frontend Tests (vitest)
- [ ] API client module (mock fetch)
- [ ] Utility functions (formatCurrency, escapeHtml)
- [ ] Router hash navigation

## Running Tests

```bash
# All backend tests (unit + API)
cd backend && .venv/Scripts/python -m pytest tests/ -v

# Integration tests
cd backend && .venv/Scripts/python -m pytest ../tests/integration/ -v

# All tests
cd backend && .venv/Scripts/python -m pytest tests/ ../tests/integration/ -v

# Frontend type-check
cd frontend && npx tsc --noEmit
```
