# SEO Enhancement Plan

## Goal

Make `munirevenue.com` discoverable for Oklahoma municipal and county revenue searches without undermining the application experience.

The site should be able to rank for intent such as:

- Oklahoma city sales tax revenue
- Oklahoma county use tax trends
- municipal revenue intelligence Oklahoma
- city sales tax anomalies
- missed filings Oklahoma city tax
- `[city name] Oklahoma sales tax data`
- `[county name] Oklahoma revenue trends`

## Current Constraints

The current stack is not SEO-ready for indexable content pages:

- the frontend is a Vite SPA
- routing is hash-based (`#/city/0955`, `#/county/Tulsa`)
- the HTML shell has only a single global `<title>`
- there are no page-specific descriptions, canonicals, or social tags
- there is no `robots.txt`
- there is no `sitemap.xml`
- there is no structured data
- key page content depends on client-side rendering

Important nuance:

- FastAPI already serves `index.html` for arbitrary non-API paths, so the backend can support real path-based routes.
- The blocker is the frontend router and metadata model, not the server fallback.

## Recommended Architecture

### Recommendation

Use a hybrid public-site plus app architecture:

- public, indexable pages at stable path URLs
- interactive analysis app at stable app URLs
- prerendered or static HTML for public landing pages
- client-side app hydration for deeper exploration

Recommended URL shape:

- `/`
- `/oklahoma-cities`
- `/oklahoma-cities/{city-slug}`
- `/oklahoma-counties`
- `/oklahoma-counties/{county-slug}`
- `/insights/anomalies`
- `/insights/missed-filings`
- `/industries/{naics-slug}` later
- `/app/...` for the heavier exploratory application over time

### Why this is the right path

- Search engines index normal path URLs more reliably than hash-fragment routes.
- Public landing pages need server-deliverable or prerendered HTML, not only JS-rendered content.
- If the product later moves to proxy/OIDC auth, the public SEO surface and the logged-in app surface should already be separated.

### What not to do

- Do not rely on hash routes for indexable pages.
- Do not rely on dynamic rendering as the primary long-term SEO approach.
- Do not expose every filter/sort/query state as an indexable URL.

## Information Architecture

### Indexable pages

Pages that should be indexable:

- homepage
- Oklahoma cities directory
- Oklahoma counties directory
- city landing pages
- county landing pages
- selected insight explainer pages:
  - anomalies
  - missed filings
  - municipal revenue intelligence overview
- selected dataset/explainer pages if they have substantial descriptive copy

### Noindex or non-canonical pages

Pages that should not become primary search landing pages:

- compare tool states
- export tool
- upload/report generation flows
- arbitrary filtered app states
- duplicate route variants
- transitional hash-route URLs

## Data Sources Already Available

The repo already contains enough structured data to create a first SEO layer:

- `data/parsed/copo_directory.csv`
- `data/parsed/copo_directory.json`
- `data/parsed/jurisdiction_summary.csv`

That means the first version can generate:

- city and county directory pages
- per-jurisdiction summary pages
- basic totals, coverage windows, and tax-type coverage

without waiting on a new CMS.

## Phase 1: Technical Foundations

### 1. Move from hash routing to path routing

Frontend work:

- replace the hash router in `frontend/src/router.ts` with a History API router
- convert nav links from `#/...` to real paths
- support route params on path segments instead of hash segments
- add a compatibility redirect layer so old `/#/...` links land on the new path

Backend work:

- keep the existing FastAPI SPA fallback
- explicitly preserve `/api/*` route behavior
- optionally add a redirect for legacy hash-marketing links if a clean server-side pattern is introduced

Deployment work:

- no major infra change required for path routing
- validate that Caddy preserves all non-API paths to the app

Acceptance criteria:

- `/oklahoma-cities`
- `/oklahoma-cities/oklahoma-city`
- `/oklahoma-counties/tulsa-county`

all load directly on refresh without a hash fragment.

### 2. Add a route-level SEO metadata system

Frontend work:

- add a small metadata helper that updates:
  - `document.title`
  - `meta[name="description"]`
  - `link[rel="canonical"]`
  - Open Graph tags
  - Twitter tags
- define metadata builders per route type
- ensure each view sets metadata on render and resets it on destroy/navigation

Recommended title examples:

- `Oklahoma City Revenue Trends | MuniRevenue`
- `Tulsa County Tax Revenue Data | MuniRevenue`
- `Missed Filings Detection for Oklahoma Cities | MuniRevenue`

Acceptance criteria:

- each indexable page has a unique title and description
- canonicals resolve to the preferred `https://munirevenue.com/...` URL

### 3. Add crawl control assets

Frontend/build work:

- add `frontend/public/robots.txt`
- generate `frontend/public/sitemap.xml`
- if sitemap count grows materially, support sitemap index generation

Deployment work:

- ensure the generated files are served at:
  - `/robots.txt`
  - `/sitemap.xml`

Recommended robots behavior:

- allow indexable public pages
- disallow clearly duplicative or utility-only paths if needed

## Phase 2: Public Landing Pages

### 4. Create directory and landing-page templates

Add public page templates for:

- homepage
- cities directory
- counties directory
- city detail page
- county detail page
- anomalies explainer page
- missed filings explainer page

Each landing page should include:

- plain-language explanation of what the user is seeing
- municipal or county context
- a summary module with key totals or coverage facts
- links to related cities/counties/pages
- a clear CTA into the interactive app

### 5. Generate static or prerendered HTML

Recommended first implementation:

- generate HTML files at build time from the parsed CSV/JSON files
- write a build script that emits:
  - static HTML
  - canonical URLs
  - embedded summary JSON where useful
- keep the SPA for the deeper app experience

This is a better fit than a full framework migration right now because:

- the app is already a lightweight Vite SPA
- the repo already has local data files for static generation
- public landing pages are mostly deterministic

Example first-wave pages:

- all 77 county pages
- top 100 city pages
- then expand to all municipalities with enough data coverage

### 6. Add page copy that matches search intent

Public pages need descriptive copy, not only charts and tables.

For each city/county page include:

- what taxes are covered
- coverage date range
- how this locality compares in broad terms
- why anomalies and missed filings matter operationally
- what city clerks, finance directors, and revenue analysts can do next

This content should be templated but useful, not filler.

## Phase 3: Structured Data

### 7. Add JSON-LD for eligible pages

Recommended schema types:

- `Organization` for MuniRevenue
- `WebSite` for the site
- `BreadcrumbList` for city and county pages
- `Dataset` for pages that clearly describe public tax-revenue datasets

Potential later additions:

- `CollectionPage` / `WebPage`
- `FAQPage` if there is real FAQ content

Implementation notes:

- inject JSON-LD into the page `<head>`
- validate markup before release
- keep the data aligned with on-page visible content

## Phase 4: Measurement and Search Operations

### 8. Measurement setup

Operational tasks:

- verify `munirevenue.com` in Google Search Console
- verify the domain in Bing Webmaster Tools
- submit sitemap(s)
- track:
  - indexed pages
  - query impressions
  - CTR
  - top landing pages
  - crawl errors
  - duplicate/canonical issues

### 9. Query and landing-page iteration

Use search data to determine:

- which city/county pages gain impressions
- which queries need new explainers
- whether pages need stronger titles/descriptions
- whether public pages should expose more summary content above the fold

## Recommended Implementation Sequence

### Sprint 1

- migrate routing from hash to path
- add route metadata helper
- add canonicals
- add `robots.txt`
- add sitemap generation

### Sprint 2

- ship homepage, cities directory, counties directory
- ship county landing pages
- ship top-city landing pages
- add JSON-LD for organization, website, and breadcrumbs

### Sprint 3

- expand city coverage to all municipalities with usable summaries
- ship anomalies and missed-filings explainer pages
- add dataset schema where valid
- measure index coverage and tune titles/descriptions

## Required Code Changes By Area

### Frontend

- replace hash router implementation in `frontend/src/router.ts`
- update navigation in `frontend/src/components/sidebar.ts`
- introduce route metadata helpers
- create public landing-page views and templates
- add static-generation or prerender build scripts
- add public SEO assets in `frontend/public/`

### Backend

- keep SPA path fallback in `backend/app/main.py`
- optionally add explicit responses for sitemap or metadata endpoints if generation is server-side
- optionally expose lightweight summary endpoints if static generation needs cleaner inputs than CSV files

### Data / Build

- define slug generation rules for cities and counties
- create a page manifest from `copo_directory` plus `jurisdiction_summary`
- generate sitemap entries from the same manifest
- decide which municipalities qualify for initial rollout if some records are too thin

### Deployment

- keep canonical redirect from `www` to apex in Caddy
- preserve compression and static asset serving
- add smoke tests for:
  - homepage
  - a city page
  - a county page
  - `robots.txt`
  - `sitemap.xml`

## Product Decisions Needed

These decisions should be made before implementation starts:

1. Should the main product remain at `/` or move to `/app` over time?
2. Should all city pages be indexable immediately, or only jurisdictions with stronger data coverage?
3. Should anomaly and missed-filings pages be public explainers, public data pages, or app-only views?
4. Should static city/county pages show only summary data, or also selected charts rendered server-side/prerendered?

## Recommendation

Recommended answer set:

1. Move toward a public-site plus `/app` split, even if `/app` is introduced after the first SEO release.
2. Index all counties immediately and the top cities first, then expand.
3. Make anomalies and missed-filings public explainer pages first, with deeper interactive workflows inside the app.
4. Start with summary-first static pages and add richer prerendered visuals later.

## Definition of Done for the First SEO Release

The first SEO release is done when:

- the site uses real path routes for public pages
- the homepage, cities directory, counties directory, and first-wave city/county pages have unique metadata
- `robots.txt` and `sitemap.xml` are live
- canonical URLs are correct
- structured data is present on eligible pages
- Search Console is verified and sitemap submitted
- the deployment smoke test validates at least one public city page and one county page

## External Guidance Used

- Google Search Central: JavaScript SEO basics  
  https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
- Google Search Central: Dynamic rendering as a workaround  
  https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering
- Google Search Central: Build and submit a sitemap  
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Google Search Central: Canonical URL guidance  
  https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
- Google Search Central: Intro to structured data  
  https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
- Google Search Central: How to use Search Console  
  https://developers.google.com/search/docs/monitor-debug/search-console-start
