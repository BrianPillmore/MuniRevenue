# Municipal Contact Directory — Plan

## Purpose

Build a database of Oklahoma municipal officials for MuniRev outreach. These are the decision-makers who would benefit from municipal revenue intelligence.

## Target Roles

### Cities (~525 cities)
- **City Manager** or City Administrator
- **Finance Director** or CFO
- **Mayor** and Vice Mayor
- **City Clerk**

### Counties (77 counties)
- **All 3 County Commissioners** (District 1, 2, 3)
- **County Clerk**
- **County Treasurer**

## Data Fields

| Field | Description |
|---|---|
| jurisdiction_copo | OkTAP copo code |
| jurisdiction_name | City/county name |
| jurisdiction_type | city or county |
| role | e.g., "Mayor", "Finance Director", "County Commissioner District 1" |
| full_name | Person's name |
| email | Official email address |
| phone | Office phone number |
| website | City/county official website |
| source | Where the data was found |
| last_verified | Date of last verification |

## Data Sources

1. **Oklahoma Municipal League (OML)** — oml.org
   - Publishes directory of member cities with contacts
   - Annual conference attendee lists

2. **Association of County Commissioners of Oklahoma (ACCO)** — okacco.com
   - Lists all county commissioners by district

3. **City/county official websites**
   - Most cities publish council member info, staff directory
   - County websites list elected officials

4. **Oklahoma Secretary of State**
   - Municipal filings may include contact info

5. **Oklahoma State Auditor & Inspector**
   - Annual reports list finance contacts

## Database Schema

```sql
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    copo VARCHAR(10) REFERENCES jurisdictions(copo),
    jurisdiction_name VARCHAR(255) NOT NULL,
    jurisdiction_type VARCHAR(10) NOT NULL,
    role VARCHAR(100) NOT NULL,
    full_name VARCHAR(255),
    email VARCHAR(254),
    phone VARCHAR(20),
    website VARCHAR(500),
    source VARCHAR(500),
    last_verified DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_contacts_copo ON contacts(copo);
CREATE INDEX idx_contacts_role ON contacts(role);
```

## Estimated Scale

| Role | Count |
|---|---|
| Mayors | ~525 |
| Vice Mayors | ~525 |
| City Managers | ~200 (not all cities have one) |
| Finance Directors | ~300 |
| City Clerks | ~525 |
| County Commissioners | 231 (77 × 3) |
| County Clerks | 77 |
| County Treasurers | 77 |
| **Total** | **~2,460** |

## Approach

Phase 1: Automated research via web scraping of official websites
Phase 2: Supplement with Oklahoma Municipal League directory
Phase 3: Manual verification for top 50 cities
Phase 4: Ongoing updates (re-scrape quarterly)
