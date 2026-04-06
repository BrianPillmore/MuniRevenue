# MuniRev — Continue From Here

**Last updated:** 2026-04-03
**Repo target:** https://github.com/BrianPillmore/MuniRevenue
**Production domain:** https://munirevenue.com
**Local path:** `C:\Users\brian\GitHub\CityTax`

---

## What Was Built Today (2026-04-03)

### Contact Research Database
- All 77 Oklahoma counties covered with commissioner/clerk/treasurer contacts
- 196 cities covered (population-ranked batches 01–20 + follow-up resolution for all batches)
- 8 research agents running in background to cover remaining 371 cities (batches 21–28, files `city_contacts_batch_21.csv` through `city_contacts_batch_28.csv`)
- All follow-up MD files updated — batches 01–20 resolved or deferred with explanation
- Contact data lives in `data/raw/research_contacts/`

### Backend: Contacts Table
- New `contacts` table in `backend/app/db/schema.sql`
- `Contact` ORM model in `backend/app/models/orm.py`
- `GET /api/contacts/` — filterable by type, name, contact_type, has_email; paginated
- `GET /api/contacts/summary` — coverage stats with email/phone counts
- Import script: `scripts/import_contacts.py` — loads all CSVs into DB

### Outreach Email System
- `backend/app/services/outreach.py` — core service:
  - `provision_account()` — bulk-creates `app_users` from contacts (pre-verified, skips email flow)
  - `generate_outreach_magic_link()` — server-side 7-day magic links, no rate limit
  - `format_greeting()` — `"Dear Mayor Pillmore,"` / `"Dear Finance Director Young,"` for all contacts
  - `get_jurisdiction_tax_types()` — only includes tax types the city actually collects (no lodging card if city doesn't collect lodging)
  - `build_report_email_html()` — inline-CSS HTML email, Outlook/Gmail compatible, sponsor banner support
  - `send_report_via_resend()` — Resend API via `urllib.request`
  - `send_reports_after_import(year, month)` — **import pipeline hook**: groups recipients by jurisdiction, computes data ONCE per city/county so all recipients see identical numbers, sends personalized greetings + individual magic links
- `scripts/provision_contacts.py` — bulk-provisions `app_users` from all CSVs
- `scripts/send_monthly_reports.py` — CLI trigger (called after OkTAP import):
  ```bash
  python scripts/send_monthly_reports.py --period 2026-03
  DRY_RUN=1 python scripts/send_monthly_reports.py --period 2026-03
  TEST_EMAIL=brian@yukonok.gov python scripts/send_monthly_reports.py --period 2026-03
  ```

### GTM Strategy
- Full document at `plans/gtm_strategy.md`
- Platform is **free** for all OK cities and counties — no trial, no limit
- Revenue model: tasteful sponsor banner (OMAG recommended as first sponsor call)
- Outreach sequence: 4 touches over 18 days, all `"Dear [Title] [Last Name],"` format
- Email sent on the day OkTAP data publishes — subject: `"Yukon March 2026 Tax Data — Just Published"`
- Q2 target: 25 active city accounts, first sponsor signed by May 15

---

## In Progress (Background Agents Running)

| Agent | Task | Output file |
|---|---|---|
| City research 21 | Achille → Buffalo (47 cities) | `city_contacts_batch_21.csv` |
| City research 22 | Burbank → Gracemont (47 cities) | `city_contacts_batch_22.csv` |
| City research 23 | Grandfield → Kingston (47 cities) | `city_contacts_batch_23.csv` |
| City research 24 | Kinta → Mead (47 cities) | `city_contacts_batch_24.csv` |
| City research 25 | Medford → Pensacola (47 cities) | `city_contacts_batch_25.csv` |
| City research 26 | Peoria → Slick (47 cities) | `city_contacts_batch_26.csv` |
| City research 27 | Smithville → Union City (47 cities) | `city_contacts_batch_27.csv` |
| City research 28 | Valley Brook → Yeager (42 cities) | `city_contacts_batch_28.csv` |
| Monthly report page plan | Architecture + SQL + frontend plan | `plans/monthly_report_page.md` |

---

## Next Steps (Priority Order)

### 1. Monthly Report Page — Build It
Wait for `plans/monthly_report_page.md` to complete, then launch the implementation team.

The deep link from every outreach email lands here:
`/report/{copo}/{year}/{month}` — e.g. `/report/1234/2026/3`

Page sections (one city, one month, scrollable):
1. Header — city name, month/year, population
2. Revenue summary — actual vs forecast, by tax type (only types that city collects)
3. Missed filings — table: NAICS description, months since last filing, estimated monthly value
4. Anomalies — list with expected vs actual, deviation %, severity badge
5. NAICS industry breakdown — Highcharts bar chart, top 10 industries, YoY comparison
6. 12-month trend — Highcharts line, actual + forecast overlay, current month highlighted
7. YoY comparison table by tax type
8. Footer — OkTAP data source note

### 2. Load Contacts into Database
Once research agents finish (batches 21–28 complete):
```bash
cd backend && python ../scripts/import_contacts.py
```

### 3. Provision User Accounts
```bash
cd backend && python ../scripts/provision_contacts.py
```
Creates `app_users` rows for every contact that has an email, pre-verified, linked to their jurisdiction.

### 4. Resend Setup + Test
- Sign up at resend.com, get API key
- Add to `.env`:
  ```
  RESEND_API_KEY=re_your_key_here
  MUNIREV_OUTREACH_FROM=reports@munirev.com
  MUNIREV_OUTREACH_LINK_TTL_DAYS=7
  ```
- Dry-run test: `DRY_RUN=1 TEST_EMAIL=brian@yukonok.gov python scripts/send_monthly_reports.py --period 2026-03`
- HTML output lands in `data/dry_run_reports/`

### 5. Sponsor Banner
- First call: OMAG (Oklahoma Municipal Assurance Group) — already OML-connected, natural fit
- Once signed, add to `.env`:
  ```
  MUNIREV_SPONSOR_NAME=OMAG
  MUNIREV_SPONSOR_URL=https://omag.org
  MUNIREV_SPONSOR_LOGO_URL=https://...
  ```

### 6. Invite a Co-Worker Feature
Still to be designed and built. Simple concept:
- Logged-in user sees "Invite a colleague" button on account page
- Enter colleague's email → system calls `provision_account()` for same jurisdiction
- Sends them a personalized welcome magic link email via Resend
- Backend: `POST /api/account/invite` with `{email}`
- No approval flow — just provision and send

### 7. Wire Import Pipeline Hook
Connect `send_reports_after_import(year, month)` to the OkTAP import completion.
The right spot is marked with a `# TODO` comment in `outreach.py`.
Check `backend/app/api/oktap.py` or the relevant import service for where imports complete.

---

## Key Environment Variables Needed

```bash
# Auth (already required)
MUNIREV_AUTH_MAGIC_LINK_ENABLED=true
MUNIREV_AUTH_MAGIC_LINK_BASE_URL=https://munirevenue.com
MUNIREV_AUTH_SESSION_SECRET=<strong random secret>

# Outreach email via Resend
RESEND_API_KEY=re_your_key_here
MUNIREV_OUTREACH_FROM=reports@munirev.com
MUNIREV_OUTREACH_LINK_TTL_DAYS=7

# Optional sponsor banner
MUNIREV_SPONSOR_NAME=
MUNIREV_SPONSOR_URL=
MUNIREV_SPONSOR_LOGO_URL=
```

---

## Key Files Reference

| File | Purpose |
|---|---|
| `data/raw/research_contacts/` | All contact CSVs and followup MDs |
| `backend/app/db/schema.sql` | Full DB schema incl. contacts table |
| `backend/app/models/orm.py` | All ORM models incl. Contact |
| `backend/app/api/contacts.py` | `/api/contacts/` endpoints |
| `backend/app/services/outreach.py` | Magic links, HTML email, Resend delivery |
| `scripts/import_contacts.py` | Load all CSVs into contacts table |
| `scripts/provision_contacts.py` | Create app_users from contact emails |
| `scripts/send_monthly_reports.py` | CLI trigger for monthly outreach emails |
| `plans/gtm_strategy.md` | Full GTM strategy (free model + sponsor) |
| `plans/monthly_report_page.md` | Report page architecture plan (in progress) |

---

## Auth / Magic Link System (Previously Implemented)

The magic link auth system was already fully built before today's session:
- `backend/app/user_auth.py` — token generation, session management
- `backend/app/api/account.py` — profile CRUD, jurisdiction interests, follow-ups
- `frontend/src/auth.ts`, `router.ts`, `views/login.ts`, `views/account.ts`
- Protected routes: `/forecast`, `/anomalies`, `/missed-filings`, `/account`
- Public routes remain public without login

Today's work extended this system to support server-side provisioning (no HTTP Request needed) and long-TTL outreach tokens.

---

## Continuation Prompt for Next Session

> Continue from `C:\Users\brian\GitHub\CityTax`. Read `continue.md` first.
>
> Key priorities for next session:
> 1. Check if background agents finished — city contact batches 21–28 and `plans/monthly_report_page.md`
> 2. Build the monthly report page at `/report/{copo}/{year}/{month}` per the plan
> 3. Run `scripts/import_contacts.py` then `scripts/provision_contacts.py`
> 4. Configure Resend and do a dry-run test email
> 5. Build "invite a co-worker" on the account page
> 6. Hook `send_reports_after_import()` into the OkTAP import pipeline
