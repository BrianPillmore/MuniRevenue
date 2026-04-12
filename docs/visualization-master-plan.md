# MuniRevenue Visualization Master Plan

**Branch:** `claude/munirevenue-expansion-plan-5G59s`
**Date:** 2026-04-12
**Scope:** Deep, implementable plan to expand MuniRevenue.com into a best-in-class revenue visualization and visual-analysis platform for Oklahoma municipal and county tax intelligence.

---

## Context

MuniRevenue.com is Oklahoma's public-sector tax intelligence platform — a TypeScript SPA + FastAPI + PostgreSQL monorepo serving ~644 jurisdictions (567 cities, 77 counties), 78k+ ledger records, and 9M+ NAICS records from Oklahoma Tax Commission OkTAP exports. It already ships rich features (forecasting with SARIMA/Prophet/ensemble, anomaly detection, missed-filings cache, monthly executive reports, magic-link auth, saved watchlists on anomalies/missed-filings).

**Why expand now.** The charting layer has stalled at "functional but flat." Every view hand-writes `Highcharts.chart(el, {...})` with its own inline tooltip formatter; there is no shared chart factory, no drilldown module, no treemap/heatmap/waterfall/scatter/slope, no peer-group framework, no URL-backed filter state, no revision/preliminary marking, no contribution decomposition UI, no narrative insight layer, and accessibility is explicitly disabled. The product has the data to answer "what changed and why?" — it cannot yet show it.

**Intended outcome.** A visualization system in which any user (city manager, finance director, economic development officer, analyst, journalist) can move from summary to root cause in under two minutes — with charts that are defensible in a council meeting, shareable as a link, downloadable as PNG/CSV/PDF, and seasonally-aware by default. The plan is phased into four releases (Foundation → Visualization expansion → Peer/decomposition → Narrative/export).

**Observed repo snapshot (current state — do not assume greenfield).**
- Frontend: Vanilla TypeScript, Vite 5, Highcharts **core only** (v12.5.0), custom History API router (`frontend/src/router.ts`), 17 view files, 7 shared components, single CSS file with custom properties. No React/Vue. Each view manages its own module-level `let` state. Tax toggle lives in `?tax=` query param; most other filter state is lost on refresh.
- Backend: FastAPI + PostgreSQL. Raw psycopg2 with SQL window functions (MoM/YoY already computed); SQLAlchemy ORM for writes. Materialized views: `mv_monthly_revenue_by_city`, `mv_top_naics_by_city`, `mv_yoy_comparison`. Forecasting service is sophisticated; persistence is in `forecast_runs` / `forecast_predictions` / `forecast_backtests`.
- Highcharts modules loaded: **none** beyond core. No drilldown, stock, boost, heatmap, treemap, maps, annotations, accessibility, exporting.
- Chart inventory: line (statewide trends, city revenue, county, compare, forecast, report), horizontal bar (top 10), column/boxplot (seasonality), table-with-sparklines (industry — manual row-click, not Highcharts drilldown).
- Deployment: Single Hetzner VM, Docker Compose, Caddy, FastAPI serves the Vite-built SPA from `/app/frontend/dist`.

This plan is written against that snapshot. Every recommendation below cites either an existing file to refactor or a new file to add.

---

## Table of Contents

1. Executive product vision
2. User personas and jobs-to-be-done
3. Analytic question taxonomy
4. Visualization system blueprint (chart catalog)
5. Drill-down / drill-through architecture
6. Tooltip / hover design system
7. Time comparison framework
8. Metrics and derived analytics
9. Page-by-page expansion plan
10. Information architecture & navigation
11. Highcharts implementation strategy
12. UX standards & design rules
13. Benchmarking & peer-group framework
14. Advanced analytical features
15. Data governance, trust, methodology
16. Engineering roadmap (4 phases)
17. API contract recommendations
18. Reporting, export, shareability
19. Concrete deliverables (backlogs, matrices, checklists)
20. Final recommendations (top-10s)
21. Proposed sub-documents (outlines)
22. Critical file list
23. Verification plan

---

## 1. Executive Product Vision

**North Star.** MuniRevenue.com is the trusted, explainable system of record for understanding how and why sales-tax revenue moves in Oklahoma cities and counties — giving every city manager, finance director, economic development officer, journalist, and consultant a two-minute answer to "what changed, why, and what should I do?" that is defensible in a council meeting.

**Product principles (enforce in design review):**

1. **Defensibility over cleverness.** Every number MUST be reproducible from a methodology page and a downloadable CSV. If a chart cannot be explained to an elected official in 30 seconds, it is wrong.
2. **Monthly cadence is the heartbeat.** Oklahoma OTC remits monthly; all defaults MUST align to month-end. Weekly/daily framing is forbidden.
3. **Small-numbers humility.** Cities under ~2,500 population swing wildly; the UI MUST surface volatility context (CV, peer band) before letting users draw conclusions.
4. **Seasonality first, trends second.** Every "is this bad?" question MUST be answered with a seasonally-aware reference (same-month last year, seasonal index, peer median) before a raw trend line.
5. **Revisions are first-class.** Preliminary / revised / final states MUST be visually marked in every chart and tooltip — not hidden in a footnote.
6. **Public money deserves plain language.** No NAICS-6 jargon without a human label. No "stochastic gradient anomaly score." Call it "Unusual drop vs. last year."
7. **Contribution over correlation.** When revenue moves, the UI MUST answer "which industries / tax types drove it" with a contribution decomposition — not a scatter plot for users to interpret.
8. **Peer context is non-optional.** Every city KPI MUST be paired with a peer-group position (percentile, rank, band) from day one.
9. **One chart, one question.** No dual-axis traps, no 12-series spaghetti. If a view needs more, use small multiples.
10. **Exportability is a feature.** Every chart MUST be downloadable as PNG and CSV; every page MUST have a shareable URL that round-trips all filter state.

---

---

## 2. User Personas and Jobs-To-Be-Done

Oklahoma-specific framing: sales tax is the dominant general-fund revenue source for cities (often 60–80%), collected by OTC and remitted monthly. Small cities are volatile. Tourism/lodging cities (Grove, Hochatown, lake communities) have extreme summer seasonality. Energy-adjacent counties (Kingfisher, Woods) swing with rig counts. Metro-adjacent cities (Edmond, Jenks, Bixby) compete with each other for retail.

### Persona A — City Executive (Mayor, City Manager)
Goals: defend the budget, know the headline direction, communicate with council.
Data literacy: moderate. Needs one-line answers with a citation.
Top 10 questions:
1. Did we beat budget this month?
2. Are we up or down vs. last year, and is it seasonal?
3. How do we compare to peer cities this fiscal year?
4. Which industries are driving our growth or decline?
5. Are any major filers missing?
6. Is a downturn starting or is this noise?
7. How dependent are we on one sector or one retailer?
8. What should I say at Tuesday's council meeting?
9. Is our per-capita revenue competitive with peers?
10. How does our sales-tax trajectory look for the next 6 months?

### Persona B — Finance Director
Goals: reconcile budget, explain variance, forecast revenue.
Data literacy: high. Comfortable with NAICS, fiscal year.
Top 10:
1. What is the current-month preliminary vs. final number?
2. What is trailing-12-month (T12M) revenue and is it decelerating?
3. What is the forecast variance vs. actual YTD?
4. MoM and YoY breakdown by tax type (general, use, dedicated)?
5. Which NAICS sectors had the largest dollar contribution to change?
6. Are any filers late or missing vs. baseline?
7. What is our revenue concentration (HHI) and is it rising?
8. What is our seasonal index and is this month above/below normal?
9. Has OTC revised prior months?
10. What do conservative vs. optimistic forecast scenarios imply for budget?

### Persona C — Economic Development Officer
Goals: track industry mix shifts, spot new retail openings, pitch site selectors.
Data literacy: moderate to high.
Top 10:
1. What industries are gaining share in my city?
2. How do we compare to regional peers in retail, accommodation, food service?
3. Is a new development project showing up in NAICS data?
4. Which sectors are we losing to a neighbor?
5. What is our tourism intensity vs. peer group?
6. Is our industry mix diversifying or concentrating?
7. Where are we outperforming the statewide sector trend?
8. Which peer cities grew fastest in my target sector?
9. What is per-capita retail revenue vs. metro average?
10. What does our industry profile look like on a treemap vs. a peer?

### Persona D — County Official
Top 10:
1. What is our county-wide trend?
2. Which cities within the county are pulling revenue up or down?
3. How does our county compare to adjacent counties?
4. Are unincorporated sales shifting to a specific city?
5. What's the industry mix at the county level?
6. Are we tracking the statewide median?
7. What's our forecast confidence interval?
8. Any anomalies in member cities this month?
9. How seasonal is our county vs. state?
10. How does the energy sector affect us? (where applicable)

### Persona E — Analyst / Consultant
Top 10:
1. Give me the raw ledger for multi-year analysis.
2. Let me compare any 2–5 cities on any metric.
3. Give me peer groups by population, metro, tourism.
4. Let me index cities to 100 at a chosen base month.
5. Show me contribution to growth decomposition.
6. Give me backtest accuracy for forecasts.
7. Give me a downloadable chart pack for a client.
8. Let me annotate events (tax rate change, new mall opening).
9. Let me filter NAICS to 6-digit.
10. Give me an API token (future).

### Persona F — Journalist / Researcher
Top 10:
1. Which Oklahoma city grew fastest last year?
2. Which declined fastest?
3. What's the statewide trend story?
4. How did the pandemic reshape sales tax?
5. Is rural Oklahoma losing ground?
6. Which sectors dominate Oklahoma revenue?
7. What does the methodology say about reliability?
8. Can I cite a direct URL for a chart?
9. Is there a PNG I can drop into a story?
10. Where does the data come from?

---

## 3. Analytic Question Taxonomy

| Category | Definition | Why it matters (OK context) | Best visuals | Required interactions | Supporting detail table |
|---|---|---|---|---|---|
| **Status** | Where are we right now? | Council meeting opener | KPI card, bullet chart, big-stat | Period switcher, tax-type toggle | Latest-period table with prelim/final flag |
| **Trend** | How has it moved over time? | Identify turning points | Line (raw + smoothed), area, stock-style range selector | Smoothing, trendline, range selector, log toggle | Monthly table with MoM/YoY |
| **Comparison** | Us vs. peer / prior period | Accountability | Slope chart, dumbbell, small-multiple bars, index-to-100 line | Peer picker, period picker | Rank + delta table |
| **Composition** | What is it made of? | Industry mix, tax-type mix | Treemap, stacked bar, 100% stacked column | Hover reveal %, drill into slice | Hierarchical table |
| **Ranking** | Who is top/bottom? | Local pride / pressure | Horizontal bar with quantile bands, lollipop | Sort, metric swap, peer filter | Full ranked table |
| **Contribution** | What caused a change? | "Why are we down 4%?" | Waterfall, variance bar, contribution bar ($) | Period pair picker | Contribution table by NAICS |
| **Variance vs expected** | Actual vs forecast or baseline | Forecast credibility | Line + confidence band, forecast-variance bar | Scenario picker | Variance table |
| **Seasonality** | How does the month usually behave? | Lodging, holiday retail | Heatmap year × month, seasonal-subseries, index | Year focus, 3- vs 10-year baseline | Seasonal index table |
| **Concentration** | Is revenue over-dependent? | Risk framing | Pareto bar, HHI gauge, Lorenz curve | Threshold slider | Top-N table with pct share |
| **Outlier / Anomaly** | What doesn't belong? | Missed filings, fraud, one-offs | Strip plot, z-score bar, annotated line | Click to decompose | Anomaly list |
| **Peer** | Where do I stand? | Benchmarks | Percentile strip, scatter (peer cohort), bullet chart | Cohort picker | Peer table |
| **Root cause** | Drill into why | Action-orientation | Decomposition waterfall + linked NAICS table | Click through | Driver detail |
| **Geographic** | Where on the map? | County/region views | Choropleth (county), bubble map (cities), small-multiple maps | Legend toggle, region zoom | Geo table |
| **Industry** | NAICS-level structure | Diversification | Treemap, slope of industry rank, heatmap sector × month | Drill 2→4→6 digit | Industry table |
| **Tax-type** | General vs. use vs. dedicated | Policy relevance | Stacked area, small multiples | Toggle | Type table |

For every category: the taxonomy above maps directly to the chart catalog in §4 and the metrics registry in §8. Views in §9 reference these categories to decide which visuals to render by default.

---

## 4. Visualization System Blueprint — Chart Catalog

All charts MUST be produced by a shared factory (`frontend/src/charts/factory.ts`, NEW — see §11). Every chart registers a **level tag** (`state | county | city | city-industry | tax-type | peer`) used by the drill-down router in §5.

### 4.1 Core time-series
1. **Monthly revenue line (raw)** — Highcharts `line`. Fields: `period, amount, is_preliminary`. Tooltip: MoM, YoY, seasonal index, T12M. Drill: click point → `/report/:copo/:year/:month`. Levels: state, county, city, tax-type. Misuse: never overlay >4 series.
2. **Monthly revenue line with confidence band** — `arearange` + `line` (needs `highcharts-more`). For forecast + historical.
3. **T12M (trailing 12-month) line** — `spline`. Removes seasonality; default on Finance Director landing.
4. **Index-to-100 comparison line** — `line`. Multi-city rebased to a chosen month. Compare view. Never mix with raw dollars.
5. **Stock-style range selector line** — `highcharts/modules/stock`. For 10+ year history.

### 4.2 Change / contribution
6. **MoM bar chart** — `column`, diverging colors (teal up / warm-orange down). Always chronological.
7. **YoY bar chart** — monthly or FY.
8. **Waterfall contribution chart** — `waterfall` (from `highcharts-more`). Decomposes Period A → Period B by NAICS or tax type. MUST be the "why" visual everywhere a change is shown.
9. **Variance-vs-forecast bars** — `column` centered at zero. Forecast view.

### 4.3 Composition
10. **Industry treemap** — `highcharts/modules/treemap`. Fields: `naics_code, naics_label, pct_of_total, yoy_pct`. Color = YoY, size = share. Drill 2→4→6 digit. **MUST replace the current manual row-click sparkline pattern in `frontend/src/views/city/industry-tab.ts`.**
11. **Tax-type stacked area** — `areaspline` stacked. City, state.
12. **Pareto bar** — `column` + `spline` cumulative. Concentration.
13. **100% stacked column by year** — `column` stacked percent. Mix drift.

### 4.4 Comparison / peer
14. **Slope chart** — `line` with two categorical x-values (FY24 vs FY25) per city. Peer compare. Use instead of twin bar charts for rank changes.
15. **Dumbbell chart** — from `highcharts-more`. Min/max or peer range.
16. **Peer scatter** — `scatter`, x = population, y = per-capita revenue. Needs `boost` module for >500 cities.
17. **Small multiples grid** — CSS grid of `line` charts, one per peer. Implement as `createChartGrid()` in factory.
18. **Percentile strip / barcode chart** — `scatter` with tight x-range; single-city highlighted dot.

### 4.5 Seasonality
19. **Year-by-month heatmap** — `highcharts/modules/heatmap`. X = month, y = year, color = YoY% or seasonal index. **MUST be the primary seasonality visualization** (current boxplot demotes to secondary).
20. **Seasonal subseries plot** — 12 mini line charts (one per month) via factory grid.
21. **Seasonal index radial** — polar `line`. NICE-TO-HAVE, exec audience only.

### 4.6 Outlier / anomaly
22. **Annotated line with anomaly dots** — `line` + `scatter` overlay + `annotations` module.
23. **Z-score strip** — horizontal `scatter` with threshold bands.
24. **Missed-filings dot plot** — `scatter` with baseline reference line.

### 4.7 Geographic
25. **County choropleth** — `highcharts/modules/map` + Oklahoma county TopoJSON (bundle under `frontend/public/maps/ok-counties.topo.json`).
26. **City bubble map** — `mapbubble`, bubble size = revenue, color = YoY.

### 4.8 Miscellaneous
27. **Bullet chart** — `bar` + `plotBands`. KPI vs target/peer median.
28. **HHI gauge** — `solidgauge` (from `highcharts-more`). Concentration risk.
29. **Funnel of revision states** — NICE-TO-HAVE. Prelim → revised → final counts.

**When NOT to use — hard rules:**
- **No pie charts.** Treemap or bar replaces them.
- **No radar charts for analysts.** They mislead on magnitude.
- **No dual-axis line** (revenue + rate). Use small multiples.
- **No word clouds, no 3D columns.**
- **No raw MoM on tourism cities without a seasonal reference.**

---

## 5. Drill-down / Drill-through Architecture

**Canonical path.** `Statewide Dashboard → County → City → (Tax-Type | NAICS sector → NAICS 4 → NAICS 6) → Month detail → Report page.`

The current router is `frontend/src/router.ts` (History API), with routes registered in `frontend/src/main.ts` and URL builders in `frontend/src/paths.ts`. It MUST be extended, not replaced.

### 5.1 URL state encoding (MUST — Phase 1)
All filter state belongs in the URL query string and is parsed by a new module `frontend/src/state/filters.ts` exporting `parseFilters(search: string): FilterState` and `serializeFilters(state: FilterState): string`. Example:

```
?copo=5550&county=Tulsa&tax=sales&period=FY2026&compare=YoY
&metric=revenue&naics=722&smoothing=t12m&index_base=2019-01&peers=band-25k-50k
```

Every view (`frontend/src/views/*.ts`) MUST call `parseFilters(window.location.search)` on mount and push a new URL via `router.navigate()` on any control change. This replaces the current pattern where most views use module-level `let` variables (e.g., in `compare.ts`, `trends.ts`, `city.ts`) that do not survive refresh.

### 5.2 Breadcrumb component (MUST — Phase 1)
New file `frontend/src/components/breadcrumb.ts`. Renders:
`Oklahoma › Tulsa County › Broken Arrow › Retail (NAICS 44–45) › Apr 2026`
Each crumb is a link that strips the finer filters. Used on city views, report page, county view, industry explorer.

### 5.3 Exact drill pathways

| From | Click target | To | Mechanism |
|---|---|---|---|
| State monthly line | A point | `/rankings?period=YYYY-MM` (top movers) | `router.navigate` |
| State choropleth | A county | `/county/:name` | existing route |
| County view | City row | `/city/:copo` | existing |
| City revenue tab line | A point | `/report/:copo/:year/:month` | existing `report_page` endpoint |
| City industry treemap | NAICS-2 node | same view, `?naics=44` | Highcharts `drilldown` + URL sync |
| City industry treemap | NAICS-4 node | same view, `?naics=441` | drilldown event writes URL |
| City industry treemap | NAICS-6 leaf | side panel `frontend/src/views/city/industry-detail-panel.ts` | panel open |
| Waterfall bar | NAICS bar | filters treemap + linked line | cross-chart event bus |
| Anomaly dot | A date | `/city/:copo/anomalies/:date` (decompose view) | existing decompose endpoint |
| Peer slope chart | A city | `/city/:copo?peers=<same-group>` | URL sync |

### 5.4 What stays in-panel vs replaces the view
- **In-panel** (side panel, context preserved): industry NAICS-6 detail, anomaly decompose, peer detail card, revision history.
- **Replaces view** (full-page navigation): switching geography (city/county), switching report month, switching peer cohort page.

### 5.5 Deep links & shareability (MUST)
Every drill state IS a URL. A "Copy link" button in `frontend/src/components/chart-download.ts` copies `window.location.href`. A `?saved=<id>` param resolves to a saved view from `user_profile_preferences` (see §18).

Preserved across drill actions: `tax`, `period`, `compare`, `metric`, `peers`, `smoothing` — everything except geography and NAICS which are the drill axes.

---

## 6. Tooltip / Hover Design System

Tooltip formatting currently lives inline in every view. Consolidate into `frontend/src/charts/tooltips.ts` (NEW — Phase 1).

### 6.1 Specs per chart family

**Time-series tooltip** — header: bolded period with prelim flag if applicable. Body lines:
- `Revenue: $X,XXX,XXX`
- `vs prior month: ±X.X% ($±XX,XXX)`
- `vs same month last year: ±X.X% ($±XX,XXX)`
- `Seasonal index (10-yr): 1.07 (above normal)`
- `T12M: $XXX,XXX,XXX`
- Mini-sparkline (24 months) rendered as inline SVG via `renderSparkline(points)` helper.

**Composition tooltip (treemap / stacked bar)** — header: NAICS label + code. Body:
- `Share of total: XX.X%`
- `Dollars: $X,XXX,XXX`
- `YoY: ±X.X% (contribution ±$XXX,XXX)`
- `Rank this period: #N of M`

**Peer tooltip** — header: city name + copo. Body: metric value, peer percentile, rank, peer median delta.

**Waterfall tooltip** — header: step name. Body: `Delta $X,XXX,XXX (±X.X%) — Share of total change: XX%`.

**Heatmap tooltip** — header: `Jun 2024`. Body: raw dollars, seasonal index, YoY, "revised" note if applicable.

### 6.2 Cross-chart hover sync (MUST — Phase 2)
New module `frontend/src/charts/linkedHover.ts` exposes `registerLinkedChart(chart, groupId)` and dispatches `CustomEvent('chart:hover', {detail:{groupId, x}})`. All charts sharing a `groupId` highlight the matching point. Use on:
- **City overview**: KPI sparklines + main line + YoY bar all linked.
- **Seasonality view**: heatmap + subseries grid linked by month.

### 6.3 Crosshair rules
- All time-series MUST enable `xAxis.crosshair`.
- Composition charts (treemap, stacked bar) MUST NOT use crosshair.
- Peer scatter MUST use both crosshairs with labels.

### 6.4 Side-panel pattern
On city overview, a persistent right-side panel (`frontend/src/components/detail-panel.ts`, NEW) listens to `chart:hover` and updates with the hovered period's full metric set. This replaces the current pattern of dumping every metric into the tooltip.

### 6.5 Formatter convention (TypeScript prose)

```
// frontend/src/charts/tooltips.ts
export const timeSeriesTooltip = (opts: { showSparkline?: boolean }) =>
  function (this: Highcharts.TooltipFormatterContextObject) {
    const ctx = this.points?.[0]?.point as EnrichedPoint;
    return [
      `<b>${fmtMonth(ctx.x)}</b> ${ctx.isPreliminary ? '<span class="tag-prelim">preliminary</span>' : ''}`,
      line('Revenue', formatCurrency(ctx.y)),
      delta('MoM', ctx.mom_pct, ctx.mom_abs),
      delta('YoY', ctx.yoy_pct, ctx.yoy_abs),
      line('T12M', formatCurrency(ctx.t12m)),
      opts.showSparkline ? sparklineSVG(ctx.trailing24) : ''
    ].join('<br/>');
  };
```

Every view (`frontend/src/views/trends.ts`, `overview.ts`, `city/*.ts`) MUST import from `tooltips.ts` rather than inline formatters. This is the refactor that delivers tooltip consistency across the site.

### 6.6 Anti-overload rules
- Max 6 lines in a tooltip; use the side panel for more.
- No tooltips on scrollable tables — highlight row inline instead.
- Never nest a tooltip inside a tooltip.

---

## 7. Time Comparison Framework

Implement in a new primitive module `frontend/src/charts/timeComparison.ts` (NEW — Phase 1) exporting reusable series transforms:

```
toT12M(points)
toT3M(points)
toYoYDelta(points)
toIndex100(points, baseMonth)
toYTD(points, fiscalStartMonth)
toSeasonalIndex(points, baselineYears)
toRollingCAGR(points, windowYears)
```

| Mode | Question | Chart form | Misinterpretation risk | Labeling rule (MUST) |
|---|---|---|---|---|
| Current month | Where are we? | KPI big-stat | Prelim confusion | Always show prelim/revised badge |
| Prior month | Near-term direction | MoM bar | Seasonal noise | Always pair with YoY |
| YoY (same month) | Seasonally clean answer | YoY bar, two-line overlay | Base effects | Annotate one-time events |
| T3M | Smoothed short-term | T3M spline | Lag | Label "3-month avg" |
| T12M | Underlying level | T12M spline | Slow to turn | Label "trailing 12-mo total" |
| YTD (CY & FY) | Budget alignment | YTD bar vs prior YTD | CY vs FY confusion | Show fiscal year indicator in header |
| Index-to-100 | Long-run comparison across sizes | Multi-line rebased | Base-month sensitivity | Show base month; allow reset |
| Seasonality overlay | Does this month behave normally? | Current year line + 5-yr band | Reading variance as trend | Show band as quantile (10/50/90) |
| Rolling averages | Smoothing | Line + T12M | Endpoint artifacts | Shade last incomplete window |
| Pre/post event | Policy / event impact | Annotated line | Cherry-picking | Require annotation text |
| Rolling CAGR | Long-run growth rate | Line of 3Y rolling CAGR | Hides volatility | Require ≥36-month history |

### 7.1 Oklahoma-specific defaults
- Default comparison for cities is **YoY of same month**, not MoM — lodging cities like Grove and Hochatown have 3× summer seasonality that makes MoM meaningless.
- Fiscal-year selector MUST default to Oklahoma FY (Jul 1 – Jun 30) for logged-in city users; CY for state/journalist users. Setting lives in `user_profile_preferences`.
- Lodging / food-service cities MUST get an auto-flag in `frontend/src/utils.ts` (`isTourismIntensive(copo)`) that switches the default smoothing to T3M and shows the seasonal band prominently.

### 7.2 Incomplete-period handling
- Latest month visibly dashed if preliminary.
- Rolling windows that include the preliminary month MUST shade the right-edge envelope.
- Tooltip for those points states: "Preliminary — subject to revision."

---

## 8. Metrics & Derived Analytics

Organize as a registry in `frontend/src/charts/metrics.ts` (NEW, frontend labels/units) paired with backend computations in `backend/app/services/metrics.py` (NEW).

Every metric row carries: `id`, `label`, `unit`, `higher_is_better: boolean | null`, `default_viz`, `supported_levels`, `caveats`, `formula`. This lets the frontend metric picker (`frontend/src/components/metric-picker.ts`, NEW) drive any generic chart view.

### Core
- **Monthly revenue** — sum of remittances; `$`, line/bar. Caveat: preliminary.
- **T12M revenue** — rolling 12-month sum; line. Caveat: insensitive near turning points.
- **Per-capita revenue** — already in `mv_monthly_revenue_by_city.returned_per_capita`; scatter/bar. Caveat: population basis year.
- **Revenue by tax type** — general/use/lodging; stacked area. Caveat: dedicated types vary by city.

### Comparative
- **MoM %, YoY %** — SQL LAG already present in `backend/app/api/cities.py:685+` and `analytics.py:491+`; bar. Caveat: seasonality for MoM.
- **YTD vs prior YTD** — bar pair. Caveat: fiscal confusion.
- **Vs peer median** — difference in $ or %; bullet chart.
- **Index-to-100** — `(value / base_value) * 100`; line.

### Composition
- **NAICS share** — `pct_of_city_total` from `mv_top_naics_by_city`; treemap. Caveat: filer reclassification.
- **Tax-type share** — stacked area.
- **Top-N concentration** — share of top 5 / top 10 NAICS; bar.

### Contribution
- **$ contribution to YoY change by NAICS** — `value_t - value_{t-12}` per NAICS, summed; waterfall. MUST be the answer to "why?".
- **Share of total change** — contribution / total change; table column beside waterfall.
- **Share gain / loss** — change in NAICS share vs prior period; slope chart.

### Volatility
- **Coefficient of variation (CV)** — `stdev / mean` over trailing 24 months; strip plot vs peers.
- **Rolling stdev (6-mo, 12-mo)** — line overlay.
- **Max drawdown vs peak** — single number. Caveat: sensitive to peak noise.

### Peer
- **Peer percentile rank** — per metric within cohort; badge on KPI.
- **Peer median / p25 / p75** — reference lines on city charts.
- **Distance to peer median** — % or $; bullet chart.

### Concentration
- **HHI by NAICS** — `sum((share_i)^2) * 10000`; solidgauge. Caveat: sensitive to NAICS detail level.
- **Top-1 dependency** — largest filer group share; red badge if >30%.
- **Breadth of growth** — share of NAICS-4 sectors with YoY > 0; bar. Caveat: requires ≥24 active sectors.
- **Lorenz curve / Gini** — NICE-TO-HAVE.

### Anomaly
- **Z-score vs expected** — `(actual - baseline) / stdev`; strip with bands.
- **Missed-filing count & dollar estimate** — already computed in `analytics.py` missed-filings endpoint.
- **Revision magnitude** — `abs(final - prelim) / prelim`; methodology page.

---

## 9. Page-by-Page Expansion Plan

### 9.1 Existing pages to upgrade

**Overview (`frontend/src/views/overview.ts`)** — target user: mixed exec & journalist. Above-the-fold: 4 KPI cards (latest-month $, YoY %, YTD vs prior, active city count) + annotated statewide monthly line with anomaly dots. Secondary: county choropleth, top-10 movers dumbbell, industry treemap statewide. Tables: latest 12 months statewide detail. URL-bound filters: tax-type, period range, CY/FY. Default: last 36 months, FY, all tax types. Mobile: KPI cards stack, choropleth → ranked bar.

**Trends (`frontend/src/views/trends.ts`)** — add index-to-100 mode, rolling CAGR mode (via `timeComparison.ts`). Add range selector (Highcharts stock module). Keep existing smoothing/seasonal/trendline controls in `chart-controls.ts` but wire them to URL state.

**Rankings (`frontend/src/views/rankings.ts`)** — add peer-cohort filter pill (populated from new `/api/stats/peer-group`). Add dumbbell and slope chart toggles. Keep revenue-band filter.

**Compare (`frontend/src/views/compare.ts`)** — replace current layout with small-multiples grid. Add index-to-100 as primary mode. Add shareable URL (currently state is lost on refresh).

**County (`frontend/src/views/county.ts`)** — add choropleth of cities within county. Add contribution waterfall (which cities drove county change).

**Forecast (`frontend/src/views/forecast.ts`)** — add backtest accuracy display (pull from `forecast_backtests`). Variance-vs-forecast bar below main line. Scenario comparison slope chart.

**Anomalies → Anomaly Center v2 (`frontend/src/views/anomalies.ts`)** — strip chart of z-scores by city. Click an anomaly → decompose panel with contribution waterfall. Saved anomaly list for a watchlist.

**Missed-filings (`frontend/src/views/missed-filings.ts`)** — baseline-method picker moved to header. Dot plot with baseline reference line.

**Report (`frontend/src/views/report.ts`)** — keep structure; add waterfall contribution for the month. Add "Copy link" and "Download chart pack" buttons.

**City tabs (`frontend/src/views/city/*`)**:
- `overview-tab.ts` — KPI cards with peer percentile badges, annotated line, HHI gauge, top-NAICS pareto.
- `revenue-tab.ts` — full time-comparison suite, tax-type stacked area.
- `industry-tab.ts` — **replace manual row-click with Highcharts drilldown treemap 2→4→6**. Waterfall below for contribution.
- `seasonality-tab.ts` — heatmap year×month + subseries grid + seasonal index line. Replaces boxplot-only view.
- `details-tab.ts` — filers, revisions log, methodology anchor.

### 9.2 New pages

**Statewide Dashboard v2 (`frontend/src/views/dashboard.ts`, NEW)** — exec-mode landing. Big KPI stats, choropleth, top-movers, narrative callouts.

**Peer Compare (`frontend/src/views/peer-compare.ts`, NEW)** — uses `/api/stats/peer-group/{id}/rankings`. Small multiples + slope chart + percentile strip.

**Industry Explorer (`frontend/src/views/industry.ts`, NEW)** — statewide treemap drill 2→4→6. Sector × city heatmap. Sector time series.

**Seasonal Analysis (`frontend/src/views/seasonality.ts`, NEW)** — city-agnostic; pick any city/state/tax-type and explore seasonality.

**Economic Pulse (`frontend/src/views/pulse.ts`, NEW)** — uses `economic_indicators` table. Overlays rig count, unemployment, lodging tax onto revenue.

**Watchlist (`frontend/src/views/watchlist.ts`, NEW)** — user-defined list of cities with last month's deltas, anomaly badges, peer positions. Requires `user_watchlist` table (new migration in `backend/alembic/versions/`).

**Download Center (`frontend/src/views/downloads.ts`, NEW)** — chart-pack PDFs, CSV exports, methodology PDFs.

**Methodology (`frontend/src/views/methodology.ts`, NEW)** — upgrade from `about.ts`. Data sources, latency, revision policy, suppression, NAICS, forecast models, backtest accuracy.

---

## 10. Information Architecture & Navigation

### 10.1 Sidebar restructure (`frontend/src/components/sidebar.ts`)
Current sidebar is a flat list. Restructure into four groups:

1. **Explore** — Statewide Dashboard, Trends, Rankings, Industry Explorer, Seasonal Analysis, Economic Pulse
2. **Places** — Cities (search), Counties, Compare, Peer Compare
3. **Signals** — Anomaly Center, Missed Filings, Forecast, Watchlist
4. **Learn & Export** — Methodology, Download Center, About

### 10.2 Global vs local filters
- **Global** (persist across pages, stored in URL + localStorage): tax-type, fiscal/calendar year mode, preliminary-included toggle. Rendered as a sticky header bar (`frontend/src/components/global-filter-bar.ts`, NEW).
- **Local** (reset per page): period range, peers, metric, smoothing, NAICS scope. Extend existing `chart-controls.ts` to accept a `FilterState` from `frontend/src/state/filters.ts`.

### 10.3 Tabs vs side panels
- **Tabs** for orthogonal views of the same entity (City overview/revenue/industry/seasonality/details).
- **Side panels** for drill-through detail (NAICS-6 industry panel, anomaly decompose panel).
- **Never nest tabs.**

### 10.4 Saved views
Icon in global filter bar. Opens dropdown of saved filter states from `user_profile_preferences.saved_views` JSONB column (new column — migration required). See §18.

### 10.5 Onboarding
First-visit lightweight overlay (`frontend/src/components/onboarding.ts`, NEW) walks through 3 steps: pick a city, pick a comparison, try a drill. Dismissed permanently via localStorage.

### 10.6 Progressive disclosure
- **Exec mode:** KPI + annotated line + 3 callouts.
- **Analyst mode:** all tabs + metric picker + raw tables.
Toggle in global filter bar; persisted per user.

---

## 11. Highcharts Implementation Strategy

### 11.1 Modules to add (`frontend/package.json` + imports in `frontend/src/theme.ts`)

| Module | Why | Phase | Priority |
|---|---|---|---|
| `highcharts/modules/drilldown` | Industry treemap and bar drilldown | 1 | MUST |
| `highcharts/modules/treemap` | Industry composition | 1 | MUST |
| `highcharts/modules/heatmap` | Year × month seasonality | 1 | MUST |
| `highcharts/highcharts-more` | Waterfall, dumbbell, arearange, solidgauge | 1 | MUST |
| `highcharts/modules/accessibility` | WCAG for public-sector site | 1 | MUST |
| `highcharts/modules/exporting` | Export menu | 1 | MUST |
| `highcharts/modules/offline-exporting` | Client-side PNG/SVG (no server trip) | 1 | MUST |
| `highcharts/modules/export-data` | CSV download of underlying series | 1 | MUST |
| `highcharts/modules/annotations` | Event markers, anomaly callouts | 2 | MUST |
| `highcharts/modules/stock` | Range selector on long series | 2 | SHOULD |
| `highcharts/modules/boost` | Peer scatter with >500 points | 2 | SHOULD |
| `highcharts/modules/map` + OK county topojson | Choropleth + bubble map | 2 | SHOULD |
| `highcharts/modules/pattern-fill` | Preliminary / revised shading | 2 | NICE |

**Bundle impact mitigation:** Dynamic-import Highcharts modules per route so non-users of treemap don't pay for it. Vite supports this natively.

### 11.2 Shared chart factory — `frontend/src/charts/factory.ts` (NEW)

API shape (prose):

```
createChart(el: HTMLElement, spec: ChartSpec): ChartHandle
  spec: { type, data, metric, level, comparison, linkedGroup?, annotations?, options? }
  Returns: { chart, setData, setComparison, destroy }

createChartGrid(el, specs[]): GridHandle
createLinkedChartGroup(groupId): registers cross-hover
```

Factory internals:
1. Reads the metric registry (`frontend/src/charts/metrics.ts`) to get unit, label, default color, `higher_is_better`.
2. Applies the theme from `frontend/src/theme.ts`.
3. Attaches the correct tooltip formatter from `frontend/src/charts/tooltips.ts`.
4. Wires URL sync if `spec.syncFilter` set.
5. Registers with `linkedHover.ts` if `linkedGroup` set.
6. Adds export menu via `offline-exporting`.
7. Applies revision-state marking helper (`markRevisionState(point)`).

**Refactor target (Phase 1):** every view currently hand-writes `Highcharts.chart(el, {...})`. Replace with `createChart(el, {...})` in:
- `frontend/src/views/overview.ts`, `trends.ts`, `rankings.ts`, `compare.ts`, `county.ts`, `forecast.ts`, `anomalies.ts`, `missed-filings.ts`, `report.ts`
- `frontend/src/views/city/{overview,revenue,industry,seasonality,details}-tab.ts`

This is a mechanical refactor best done before any new charts land — otherwise new charts will inherit the old inline pattern.

### 11.3 Concrete factory examples

**Treemap (city industry tab):**
```
createChart(el, {
  type: 'treemap',
  level: 'city-industry',
  data: naicsTree,
  metric: 'naics_share',
  comparison: 'YoY',
  drilldown: { naicsDepth: [2, 4, 6], urlParam: 'naics' },
  tooltip: 'composition',
  linkedGroup: 'city-industry-' + copo
});
```

**Small-multiples peer grid:**
```
createChartGrid(el, peers.map(p => ({
  type: 'line',
  level: 'city',
  data: p.series,
  metric: 'revenue_t12m',
  title: p.name,
  linkedGroup: 'peer-' + groupId
})));
```

**Boost scatter (statewide per-capita):**
```
createChart(el, {
  type: 'scatter',
  data: allCities,
  metric: 'per_capita_revenue',
  boost: true,
  tooltip: 'peer'
});
```

**Stock range selector:**
```
createChart(el, {
  type: 'stockLine',
  data: state120m,
  metric: 'revenue',
  rangeSelector: ['1Y','3Y','5Y','10Y','All'],
  tooltip: 'timeSeries'
});
```

### 11.4 Performance considerations
- Server-side aggregation in SQL remains the source of truth (already true in `analytics.py` and `cities.py`).
- For city-level 20-year series, lazy-load data in 5-year chunks.
- For statewide peer scatter, enable `boost` once point count > 500.
- Client-side hydration: use `requestIdleCallback` for non-visible charts below the fold.

### 11.5 Accessibility
- Import `highcharts/modules/accessibility` (currently disabled in `theme.ts:49`).
- Every chart factory-produced instance MUST have `description` derived from metric label + period.
- Keyboard navigation for drilldown.

---

## 12. UX Standards & Design Rules

### 12.1 Color
- **Positive = teal `#2b7a9e`** (existing brand).
- **Negative = warm orange `#c8922a` → `#a16a12` for text, `#d97a3c` for fills — never red.**
- Neutral = navy `#1b3a5c`.
- Background = off-white `#f8f6f1`.
- Categorical palette = existing 8-color CVD-safe set in `frontend/src/theme.ts`; extend with 2 tertiary shades for treemap depth.
- **Red/green traffic-light deltas are BANNED.** Warm-orange down, teal up.

### 12.2 Typography
- Keep existing Inter (sans) + Merriweather (serif headings).
- Establish scale `12/14/16/20/28/40` in CSS vars.
- Numbers in `font-variant-numeric: tabular-nums`.

### 12.3 Spacing
- 4px base grid.
- Chart container padding 16/24.
- KPI cards 20px.
- Sidebar 240px fixed (existing).

### 12.4 States
- **Empty:** `frontend/src/components/empty-state.ts` (NEW, extending existing `loading.ts`). Text: "Not enough history for this view" + link to methodology.
- **Loading:** keep current skeleton; add per-chart shimmer.
- **Error:** standard card with "Retry" + "Report issue" links.

### 12.5 Suppression / revision / preliminary marking (MUST)
- **Suppressed:** gray hatched pattern (`pattern-fill` module). Tooltip: "Suppressed per OTC rule."
- **Preliminary:** dashed stroke on last point; pill badge in tooltip header; amber underline under KPI.
- **Revised:** small triangle marker; tooltip lists previous value.
- **Final:** solid.

Single helper `markRevisionState(point)` in `frontend/src/charts/factory.ts`.

### 12.6 NAICS framing for non-analysts
All NAICS codes MUST be accompanied by a human label from a lookup (`frontend/src/data/naics-labels.ts`, NEW) sourced at build from a backend dataset. "NAICS 722" is never shown alone; always "Food services (722)".

### 12.7 Absolute vs percentage display
- **Default to absolute** ($) for headline KPIs with percentage as a subordinate delta chip.
- **Default to percentage** for ranking and peer-compare where scales differ.
- Provide a toggle where both are meaningful, but never dual-axis.

### 12.8 Trust elements
- Chart footer component (`frontend/src/components/chart-footer.ts`, NEW) on every chart: `Source: OK Tax Commission · As of YYYY-MM-DD · [methodology]`.
- Methodology anchors deep-link to specific sections.
- Hash/fingerprint of source file shown on methodology page.

---

## 13. Benchmarking & Peer Group Framework

### 13.1 New backend table (in `backend/app/db/schema.sql`, migration in `backend/alembic/versions/`)

```sql
CREATE TABLE jurisdiction_peer_groups (
  id SERIAL PRIMARY KEY,
  copo TEXT REFERENCES jurisdictions(copo),
  group_type TEXT NOT NULL,   -- 'pop_band' | 'metro_adj' | 'tourism' | 'industry_sim' | 'tax_base' | 'county_seat'
  group_key TEXT NOT NULL,    -- e.g. '25k-50k', 'OKC-metro', 'tourism-high'
  weight NUMERIC DEFAULT 1.0,
  source TEXT,
  computed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_peer_groups_copo ON jurisdiction_peer_groups(copo);
CREATE INDEX idx_peer_groups_key ON jurisdiction_peer_groups(group_type, group_key);
```

### 13.2 New service — `backend/app/services/peer_groups.py`

| Method | Definition | Pitfalls | UI exposure |
|---|---|---|---|
| `build_pop_band_groups` | bands `{<2.5k, 2.5–10k, 10–25k, 25–50k, 50–100k, >100k}` | Population basis year drift | Default peer band on city overview |
| `build_metro_adjacency` | OKC/Tulsa/Lawton metro; distance to core < 30 mi | Misses Stillwater-type outposts | "Metro peers" pill |
| `build_county_seat_group` | flag | Oversimplifies for small seats | Secondary filter |
| `build_tourism_intensity` | accommodation+food share > statewide median + σ | Inflated by single big hotel | Seasonal page default peers |
| `build_industry_similarity` | cosine similarity of NAICS share vectors; top-5 neighbors | Unstable MoM | Analyst-mode only |
| `build_tax_base_size` | deciles of T12M revenue | Correlates heavily with population | Budget benchmarking |

### 13.3 New endpoint — `backend/app/api/peer_groups.py`

- `GET /api/stats/peer-group?copo=&type=` — resolves a city to its peer IDs per type.
- `GET /api/stats/peer-group/{group_key}/rankings?metric=&period=` — ordered list with target city flagged.

### 13.4 UI exposure (MUST — Phase 3)
- Every city KPI card gains a "vs peer" chip: `#3 of 12 in pop band 10–25k`.
- Rankings page gains a peer-cohort filter.
- Peer Compare view is built on this endpoint.
- Tooltip on any peer chip links to `/peer-compare?group=<group_key>&focus=<copo>`.

### 13.5 Peer-group pitfalls (display as caveats)
- Peer groups are a reference, not a destination. Show the methodology for each type in tooltip.
- Don't let peers hide the absolute answer — always pair a peer percentile with the raw value.
- Re-compute peer groups nightly in the same ETL batch that refreshes materialized views.

---

## 14. Advanced Analytical Features

Ranked by value × feasibility.

1. **Rule-based narrative callouts** (MUST, Phase 3) — new backend service `backend/app/services/narratives.py`; endpoint `GET /api/stats/narratives?copo=&period=` returning `[{severity, title, body, cite_chart_id}]`. Rules include: "Top industry contribution > 40% of change", "YoY outside ±2σ vs peer band", "Seasonal index deviation > 20%", "HHI rose >10% QoQ", "Missed filings estimated impact > 5% of revenue". Rendered by `frontend/src/components/narrative-callouts.ts` (NEW).

2. **Anomaly flags everywhere** (MUST, Phase 2) — tiny badge next to any period that appears in the `anomalies` table. Uses the existing anomaly endpoint.

3. **Contribution waterfalls** (MUST, Phase 2) — new endpoint `GET /api/stats/contribution?copo=&period=&comparison=` in new file `backend/app/api/decomposition.py`. Returns `[{dimension, label, delta_abs, delta_pct, share_of_total_change}]`. Used in city, county, report pages.

4. **Concentration warnings** (MUST, Phase 3) — HHI badge. Amber chip if HHI > 2500 or top-1 share > 30%.

5. **Peer percentile badges** (MUST, Phase 3) — computed server-side in peer_groups service.

6. **Seasonality-aware alerts** (SHOULD, Phase 3) — rather than "down 15% MoM," say "down 15% MoM but normal for May given 5-yr pattern."

7. **Saved watchlists** (SHOULD, Phase 4) — new `user_watchlist` table `(user_id, copo, added_at, thresholds jsonb)`. View `frontend/src/views/watchlist.ts`.

8. **Executive vs analyst mode** (SHOULD, Phase 2) — toggle in global filter bar.

9. **Event annotations** (SHOULD, Phase 4) — new table `jurisdiction_events (copo, date, kind, title, body, source)`. Admin-editable via a future admin view. Rendered via Highcharts `annotations` module.

10. **Explain-this-chart helper** (NICE, Phase 4) — `?` button above each chart opens a methodology snippet scoped to that chart id.

---

## 15. Data Governance, Trust, Methodology

Public-sector audiences need overt credibility. Build it in.

### 15.1 Methodology page (`frontend/src/views/methodology.ts`, NEW — Phase 1)
Sections:
- **Data source.** OTC monthly remittance file, loaded date, file hash. Link to `data_imports` log.
- **Latency.** "April 2026 preliminary available 2026-05-20, revised 2026-06-15, final 2026-07-15."
- **Revision policy.** Explain revisions; link to a revisions log endpoint.
- **Suppression.** <3 filers etc., visible hatched markers in charts.
- **NAICS detail.** 2/4/6-digit coverage, labeling source.
- **Forecast models.** Prophet, SARIMA, ensemble; backtest MAPE per horizon pulled from `forecast_backtests`.
- **Anomaly method.** Baseline methods from `backend/app/services/anomaly_detector.py`.

### 15.2 Chart footer (on every chart)
`frontend/src/components/chart-footer.ts` (NEW) renders: source line, "As of YYYY-MM-DD", "[methodology]" link to the correct anchor.

### 15.3 Revision log
- New view `ledger_revisions` (audit trail of updates to `ledger_records`) — requires capturing prior values on UPDATE via a trigger in `schema.sql`.
- New endpoint `GET /api/methodology/revisions?copo=&since=`.

### 15.4 Preventing over-reading of a single month
- KPI cards MUST show MoM alongside YoY and T12M.
- For cities <2,500 population, the UI MUST render a "small-city volatility" banner on the city overview.
- Preliminary-month badges and striped hatching on the last point.

### 15.5 Making it feel credible to public finance professionals
- Lead every page with the data as-of date, not the product branding.
- Show the forecast backtest MAPE prominently on the forecast view.
- Provide a downloadable methodology PDF (matches the website).
- Show "N filers included" on NAICS detail views so users know when the denominator is thin.

---

## 16. Engineering Roadmap — Four Phases

### Phase 1 — Foundation (6 weeks)
**Goals:** unify chart creation, tooltips, time-comparison primitives, URL-backed state.
**Modules added:** drilldown, treemap, heatmap, highcharts-more, exporting + offline-exporting + export-data, accessibility.
**Backend:** none new (existing materialized views cover this phase).
**Frontend:**
- Create `frontend/src/charts/{factory.ts, tooltips.ts, timeComparison.ts, metrics.ts, linkedHover.ts}`.
- Create `frontend/src/state/filters.ts`.
- Create `frontend/src/components/{breadcrumb.ts, global-filter-bar.ts, chart-footer.ts, empty-state.ts, detail-panel.ts, metric-picker.ts, onboarding.ts}`.
- Create `frontend/src/views/methodology.ts`.
- Refactor every view to use `createChart`.
**UX:** color rules, revision markers, tooltip redesign.
**Risks:** regression in existing charts. Mitigation: write snapshot tests for 10 canonical chart specs before refactor starts.
**Dependencies:** none.
**Success criteria:** 100% of charts go through factory; no inline Highcharts config in views; URL round-trips filter state on all pages; methodology page live; accessibility module enabled.

### Phase 2 — Visualization expansion (6–8 weeks)
**Goals:** new chart types + drill-down architecture.
**Modules added:** annotations, stock, boost, map, pattern-fill.
**Data:** OK county TopoJSON in `frontend/public/maps/ok-counties.topo.json` (licence-compatible source required — see open questions).
**Backend:**
- `GET /api/stats/heatmap?copo=&metric=` in new file `backend/app/api/visualization.py`.
- `GET /api/stats/contribution` in new file `backend/app/api/decomposition.py`.
- `GET /api/stats/breadth?copo=` in same file.
**Frontend:**
- Industry tab rewrite (treemap drilldown) in `city/industry-tab.ts`.
- Seasonality tab rewrite (heatmap + subseries) in `city/seasonality-tab.ts`.
- Waterfall in city/report/county views.
- Choropleth in overview + county.
- Slope + dumbbell in compare + rankings.
- New Industry Explorer and Seasonal Analysis views.
**UX:** cross-chart linked hover; exec vs analyst mode.
**Risks:** bundle size. Mitigation: dynamic imports per route.
**Dependencies:** Phase 1 factory.
**Success criteria:** at least 15 new chart types live; NAICS drill 2→4→6 works; seasonality heatmap replaces boxplot; bundle per-route <220 KB gzipped.

### Phase 3 — Peer groups + decomposition + anomaly v2 (6 weeks)
**Goals:** benchmarking and "why" everywhere.
**Backend:**
- `jurisdiction_peer_groups` table + `backend/app/services/peer_groups.py` + `backend/app/api/peer_groups.py`.
- `backend/app/services/metrics.py` for HHI, breadth, CV.
- Extend anomaly decompose endpoints for contribution-to-decline.
- Materialized view `mv_peer_group_metrics`.
**Frontend:**
- Peer Compare view.
- Percentile badges on city KPIs.
- HHI gauge.
- Anomaly Center v2.
**UX:** peer selector component; seasonality-aware alert rules.
**Risks:** peer-group misinterpretation. Mitigation: always expose group composition in tooltip.
**Dependencies:** Phases 1–2.
**Success criteria:** every city overview shows peer rank; contribution waterfall live; peer-compare small-multiples live.

### Phase 4 — Narrative / watchlist / export pack (6 weeks)
**Goals:** insight generation, shareability, premium hooks.
**Backend:**
- `backend/app/services/narratives.py` + `backend/app/api/narratives.py`.
- `user_watchlist` + `jurisdiction_events` tables.
- `backend/app/services/chart_pack.py` (client-side composition first, server headless Chromium later if needed).
- Extend `user_profile_preferences` with `saved_views` JSONB column.
**Frontend:**
- Watchlist view.
- Download Center.
- Narrative callouts component.
- Annotation editor (admin).
- Saved-views UI in global filter bar.
**UX:** share-link button, presentation mode.
**Risks:** PDF rendering complexity. Mitigation: start with client-side PNG pack composed via pdf-lib.
**Success criteria:** watchlist usable; chart pack downloadable; every chart has copy-link; at least 3 narrative rules live.

### Quick wins / medium / heavy
- **Quick wins (Phase 1):** enable exporting modules, enable accessibility, add chart footer, add copy-link button, index-to-100 toggle on compare view.
- **Medium complexity:** industry treemap drilldown, seasonality heatmap, contribution endpoint + waterfall, URL-backed filter state, shared factory refactor.
- **High-effort strategic:** peer-group framework, narrative insights, watchlist + events, server-rendered chart pack PDFs.

---

## 17. API Contract Recommendations

New endpoint families. All grouped under `/api/stats/*` and `/api/peer/*`. All reads use `get_cursor()` from `backend/app/db/psycopg.py`; writes use SQLAlchemy.

### 17.1 `GET /api/stats/contribution`
**Params:** `copo` (optional — defaults to state), `period` (YYYY-MM), `comparison` (`YoY` | `MoM` | `vsForecast`), `dimension` (`naics2` | `naics4` | `tax_type`), `level` (`state` | `county` | `city`), `limit` (default 15).
**Response:**
```
{
  "baseline_period": "2025-04",
  "target_period": "2026-04",
  "baseline_value": 1234567,
  "target_value": 1211000,
  "total_change_abs": -23567,
  "total_change_pct": -0.019,
  "dimensions": [
    { "key": "722", "label": "Food services", "baseline": 210000, "target": 230000,
      "delta_abs": 20000, "delta_pct": 0.095, "share_of_change": -0.85 }
  ],
  "residual": 4321
}
```
**Caching:** `forecast_runs`-style JSONB cache keyed by `(copo, period, comparison, dimension)` in new table `contribution_cache`.

### 17.2 `GET /api/stats/heatmap`
**Params:** `copo`, `metric` (`revenue` | `yoy_pct` | `seasonal_index`), `tax_type`, `years` (default 10).
**Response:** `{years:[...], months:[1..12], cells:[{year,month,value,is_preliminary}]}`.
**Caching:** derived from monthly series, 1 h TTL in process memory.

### 17.3 `GET /api/stats/breadth`
**Params:** `copo`, `period`, `window` (default 12).
**Response:** `{share_positive_yoy: 0.63, n_sectors: 27, sector_list:[...]}`.

### 17.4 `GET /api/stats/peer-group/{group_key}/rankings`
**Params:** `metric`, `period`.
**Response:** ordered list with target city flagged.

### 17.5 `GET /api/stats/peer-group`
**Params:** `copo`, `type` (`pop_band` | `metro_adj` | ...).
**Response:** resolves a city to its peer IDs per type.

### 17.6 `GET /api/stats/narratives`
**Params:** `copo`, `period`.
**Response:** `[{id, severity:'info'|'warn'|'critical', title, body, chart_ref, citations:[...]}]`.

### 17.7 `GET /api/methodology/revisions`
**Params:** `copo`, `since`.
**Response:** list of prelim → final deltas.

### 17.8 Precomputed summary tables (MUST — keep latency acceptable)
- `mv_peer_group_metrics` — per (peer_group_key, period, metric) rollups.
- `mv_contribution_yoy` — per (copo, period, naics2) $ deltas.
- `mv_breadth` — per (copo, period) positive-share.
All refreshed in the same nightly cron as existing MVs (`refresh_materialized_views()` in `schema.sql`).

### 17.9 API design principles
- Every analytics endpoint MUST accept `tax_type` (default `sales`), return `as_of`, and include `is_preliminary` flags on latest-period rows.
- Responses SHOULD include `caveats: string[]` for display in UI.
- Top-N + remainder: any ranking endpoint supports `top_n=10&remainder=true` so frontend can render "Top 10 + other."
- Pagination follows existing `limit/offset` convention in `analytics.py`.

---

## 18. Reporting, Export, Shareability

- **PNG/SVG per chart (MUST, Phase 1):** Highcharts `offline-exporting` module. No server trip. Hook into existing `frontend/src/components/chart-download.ts` — replace current canvas hack with Highcharts export menu.
- **CSV per chart (MUST, Phase 1):** `export-data` module. Download underlying series.
- **PDF single chart (SHOULD, Phase 2):** client-side via offline-exporting.
- **Chart pack PDF (SHOULD, Phase 4):** `backend/app/services/chart_pack.py` (NEW). Start with client-side composition (pdf-lib); upgrade to server-side headless Chromium only if needed.
- **Shareable URL with encoded filter state (MUST, Phase 1):** via `frontend/src/state/filters.ts`. A "Copy link" button on every page.
- **Saved views per user (SHOULD, Phase 4):** extend `user_profile_preferences` with a `saved_views JSONB` column. Endpoints `POST /api/account/saved-views`, `GET /api/account/saved-views`. UI in `global-filter-bar.ts`.
- **Chart pack per city (SHOULD, Phase 4):** pre-canned set of 10 charts for a city, downloadable for council packets.
- **Presentation mode (NICE, Phase 4):** full-screen chart with 24px+ fonts and keyboard nav for meetings.

**Exported artifacts MUST preserve:** title, subtitle, filter summary, period range, tax-type, source line, as-of date, methodology URL, and any active caveats — rendered in the chart's caption box.

---

## 19. Concrete Deliverables

### 19.1 Prioritized feature backlog

| # | Feature | Phase | Priority | Primary file |
|---|---|---|---|---|
| 1 | Shared chart factory | 1 | MUST | `frontend/src/charts/factory.ts` |
| 2 | URL-backed filter state | 1 | MUST | `frontend/src/state/filters.ts` |
| 3 | Tooltip system + revision marks | 1 | MUST | `frontend/src/charts/tooltips.ts` |
| 4 | Time comparison primitives | 1 | MUST | `frontend/src/charts/timeComparison.ts` |
| 5 | Accessibility + exporting modules | 1 | MUST | `frontend/src/theme.ts` |
| 6 | Methodology page | 1 | MUST | `frontend/src/views/methodology.ts` |
| 7 | Chart footer + breadcrumb | 1 | MUST | `frontend/src/components/{chart-footer,breadcrumb}.ts` |
| 8 | Global filter bar + saved views UI | 1 | MUST | `frontend/src/components/global-filter-bar.ts` |
| 9 | Industry treemap drilldown | 2 | MUST | `frontend/src/views/city/industry-tab.ts` |
| 10 | Seasonality heatmap | 2 | MUST | `frontend/src/views/city/seasonality-tab.ts` |
| 11 | Contribution waterfall + endpoint | 2 | MUST | `backend/app/api/decomposition.py` |
| 12 | County choropleth | 2 | SHOULD | `frontend/src/views/county.ts` |
| 13 | Slope + dumbbell in compare/rankings | 2 | SHOULD | `frontend/src/views/compare.ts` |
| 14 | Peer groups table + service + API | 3 | MUST | `backend/app/services/peer_groups.py` |
| 15 | Peer percentile badges | 3 | MUST | `frontend/src/components/kpi-card.ts` (refactor) |
| 16 | HHI gauge + concentration warnings | 3 | SHOULD | `frontend/src/views/city/overview-tab.ts` |
| 17 | Anomaly Center v2 | 3 | SHOULD | `frontend/src/views/anomalies.ts` |
| 18 | Narrative callouts | 4 | SHOULD | `backend/app/services/narratives.py` |
| 19 | Watchlist | 4 | SHOULD | `frontend/src/views/watchlist.ts` |
| 20 | Chart pack export | 4 | SHOULD | `backend/app/services/chart_pack.py` |
| 21 | Event annotations | 4 | NICE | new `jurisdiction_events` table |
| 22 | Presentation mode | 4 | NICE | factory extension |
| 23 | Explain-this-chart helper | 4 | NICE | `frontend/src/components/chart-help.ts` |

### 19.2 Page inventory

| Page | File | Phase | Status |
|---|---|---|---|
| Dashboard v2 | `frontend/src/views/dashboard.ts` | 1 | NEW |
| Overview (legacy, redirects) | `frontend/src/views/overview.ts` | 1 | REFACTOR |
| Trends | `frontend/src/views/trends.ts` | 1 | REFACTOR |
| Rankings | `frontend/src/views/rankings.ts` | 1 | REFACTOR |
| Compare | `frontend/src/views/compare.ts` | 1 | REFACTOR |
| County | `frontend/src/views/county.ts` | 2 | REFACTOR |
| City + tabs | `frontend/src/views/city.ts` + `city/*-tab.ts` | 1–2 | REFACTOR |
| Industry Explorer | `frontend/src/views/industry.ts` | 2 | NEW |
| Seasonal Analysis | `frontend/src/views/seasonality.ts` | 2 | NEW |
| Anomaly Center v2 | `frontend/src/views/anomalies.ts` | 3 | REFACTOR |
| Missed-filings | `frontend/src/views/missed-filings.ts` | 2 | REFACTOR |
| Forecast | `frontend/src/views/forecast.ts` | 2 | REFACTOR |
| Peer Compare | `frontend/src/views/peer-compare.ts` | 3 | NEW |
| Economic Pulse | `frontend/src/views/pulse.ts` | 3 | NEW |
| Watchlist | `frontend/src/views/watchlist.ts` | 4 | NEW |
| Download Center | `frontend/src/views/downloads.ts` | 4 | NEW |
| Methodology | `frontend/src/views/methodology.ts` | 1 | NEW |
| Report | `frontend/src/views/report.ts` | 2 | REFACTOR |

### 19.3 Drill-down path matrix

| From | To | URL change | Phase |
|---|---|---|---|
| State line → month | Rankings filtered | `?period=YYYY-MM` | 1 |
| State choropleth → county | County view | `/county/:name` | 2 |
| County → city row | City | `/city/:copo` | 1 |
| City line → month | Report | `/report/:copo/:y/:m` | 1 |
| City treemap NAICS-2 → NAICS-4 | Same view | `?naics=NN` | 2 |
| NAICS-4 → NAICS-6 | Side panel | `?naics=NNNN` | 2 |
| Anomaly dot → decompose | Panel | `?anomaly=YYYY-MM` | 2 |
| Peer slope → city | City | `/city/:copo?peers=<group_key>` | 3 |

### 19.4 Tooltip standards matrix

| Family | Module | Header | Body | Sparkline |
|---|---|---|---|---|
| Time-series | `tooltips.ts:timeSeriesTooltip` | Period + prelim tag | $, MoM, YoY, T12M | Yes |
| Composition | `tooltips.ts:compositionTooltip` | NAICS label + code | share, $, YoY contribution | No |
| Peer | `tooltips.ts:peerTooltip` | City name | metric, percentile, rank | No |
| Waterfall | `tooltips.ts:waterfallTooltip` | Step | delta, share | No |
| Heatmap | `tooltips.ts:heatmapTooltip` | Year + month | $, seasonal index, YoY | No |

### 19.5 Highcharts implementation checklist
- [ ] Add `drilldown, treemap, heatmap, highcharts-more, accessibility, exporting, offline-exporting, export-data` (Phase 1)
- [ ] Add `annotations, stock, boost, map, pattern-fill` (Phase 2)
- [ ] Create `frontend/src/charts/{factory,tooltips,timeComparison,metrics,linkedHover}.ts`
- [ ] Extend `frontend/src/theme.ts` with revision-state palette helpers
- [ ] Refactor every view to use `createChart`
- [ ] Add chart-footer + breadcrumb + global-filter-bar components
- [ ] Bundle-split per route (dynamic imports)
- [ ] Ship OK county TopoJSON under `frontend/public/maps/`
- [ ] Enable `accessibility: { enabled: true }` after module added (reverse line 49 in `theme.ts`)

### 19.6 Design-system rules checklist
- [ ] No red/green; warm-orange/teal for deltas
- [ ] Tabular numerals everywhere
- [ ] Prelim/revised/final marks on every time series
- [ ] NAICS always labeled
- [ ] All charts have a footer with source + as-of + methodology link
- [ ] All charts have export menu
- [ ] Loading/empty/error states standardized
- [ ] No dual-axis, no pie, no radar, no 3D

### 19.7 Open product / engineering questions
1. Is there an OK county TopoJSON licence-compatible with the site?
2. Are suppression rules contractually documented with OTC?
3. Which auth tier gates saved views / watchlists — all logged-in users, or premium?
4. Do we need a printable "council packet" template with city branding?
5. Who maintains event annotations — admin-only or user-submitted?
6. Are NAICS 6-digit breakdowns complete enough in `mv_top_naics_by_city` for drill-through, or is there a long-tail gap?
7. How far back should peer groups be re-computed historically?
8. Should forecast variance bars use the selected model or the ensemble?
9. Do we ship a public API token tier for analysts before or after watchlist?
10. Is server-side chart-pack PDF rendering worth the ops complexity vs. client-side?

---

## 20. Final Recommendations

### Top 10 highest-value visualization opportunities
1. Year × month seasonality heatmap per city (replaces boxplot).
2. NAICS industry treemap with 2→4→6 drilldown (replaces manual row-click sparkline in `city/industry-tab.ts`).
3. Contribution waterfall for YoY revenue change.
4. Peer percentile strip on city overview KPIs.
5. Small-multiples peer-compare grid (replaces current compare layout).
6. Statewide county choropleth with bubble-map toggle.
7. Index-to-100 multi-city overlay.
8. Annotated anomaly line on city overview.
9. HHI gauge + top-1 dependency badge.
10. Variance-vs-forecast bar chart on forecast page.

### Top 10 product mistakes to avoid
1. Dual-axis charts of dollars and percentages.
2. Red/green deltas.
3. Treating MoM as the primary delta on seasonal cities.
4. Hiding revision state in footnotes.
5. Showing NAICS codes without labels.
6. Pie charts.
7. Peer groups that don't expose their composition.
8. Narrative callouts that can't be traced back to a rule + chart.
9. Filters that don't live in the URL.
10. Premature ML anomaly explanations analysts can't reproduce.

### Top 10 implementation priorities for the first 90 days
1. Ship shared chart factory (`frontend/src/charts/factory.ts`) and refactor every existing view.
2. Ship URL-backed filter state (`frontend/src/state/filters.ts`).
3. Ship tooltip system (`frontend/src/charts/tooltips.ts`) with prelim/revised marks.
4. Ship time-comparison primitives (`frontend/src/charts/timeComparison.ts`) incl. index-to-100 and T12M.
5. Add accessibility + offline-exporting + export-data Highcharts modules.
6. Build industry treemap drilldown in `city/industry-tab.ts`.
7. Build seasonality heatmap in `city/seasonality-tab.ts` replacing the boxplot.
8. Build contribution endpoint (`backend/app/api/decomposition.py`) + waterfall chart in city and report views.
9. Build `jurisdiction_peer_groups` table + `backend/app/services/peer_groups.py` + percentile badges.
10. Build methodology page + chart footer component.

---

## 21. Proposed Sub-Documents (Outlines)

Plan mode limits me to editing this single plan file. Once the plan is approved, implementation agents SHOULD create the following documents as their first actions. Outlines below are ready to paste.

### 21.1 `docs/visualization-master-plan.md`
Purpose: canonical long-form of this plan, maintained in-repo.
Outline:
1. Vision & principles (from §1)
2. Personas & JTBD (from §2)
3. Analytic taxonomy (from §3)
4. Visualization catalog (from §4)
5. Drill-down architecture (from §5)
6. Tooltip system (from §6)
7. Time comparison framework (from §7)
8. UX standards (from §12)
9. Trust & methodology (from §15)
10. Glossary (new — NAICS levels, seasonal index, HHI, etc.)
Cross-references to `docs/metrics-dictionary.md` and `docs/highcharts-implementation-guide.md`.

### 21.2 `docs/metrics-dictionary.md`
Purpose: machine- and human-readable metric registry mirroring `frontend/src/charts/metrics.ts`.
Outline:
- For each metric: id, label, unit, formula, supported levels, default viz, higher_is_better, caveats, example SQL, source table.
- Sections: Core, Comparative, Composition, Contribution, Volatility, Peer, Concentration, Anomaly (matches §8).
- Appendix: derivations from `mv_monthly_revenue_by_city`, `mv_top_naics_by_city`, `mv_yoy_comparison`.

### 21.3 `docs/drilldown-interactions.md`
Purpose: concrete map of every click target and its destination.
Outline:
1. Navigation model (URL state, breadcrumb, back-stack).
2. Drill-down path matrix (from §19.3, expanded).
3. In-panel vs page-replace rules.
4. Linked hover groups and their member charts.
5. Deep-link format (`?saved=<id>`, `?copo=&naics=&period=` grammar).
6. Example workflows (6–8 annotated scenarios):
   - "Finance director investigates Broken Arrow April drop"
   - "Mayor preps council talking points"
   - "Analyst compares 5 tourism cities over 5 years"
   - "Journalist finds the fastest-growing city"
   - "County official decomposes county decline by member city"
   - "Economic dev officer tracks NAICS 722 share"

### 21.4 `docs/highcharts-implementation-guide.md`
Purpose: engineering reference for every Highcharts usage decision.
Outline:
1. Module inventory & rationale (from §11.1).
2. Shared factory API (`frontend/src/charts/factory.ts`) — full TypeScript signatures.
3. Tooltip formatter library — full formatter catalog.
4. Theme extension rules (`frontend/src/theme.ts`).
5. Drilldown module patterns (NAICS tree, city-to-county).
6. Treemap, heatmap, waterfall, stock, boost example configs.
7. Accessibility requirements.
8. Export menu configuration.
9. Linked hover implementation (`linkedHover.ts`).
10. Performance budget per chart type.
11. Testing patterns (snapshot of chart spec; visual regression via Playwright).

### 21.5 `plan/90-day-rollout-plan.md`
Purpose: operationalized Phase 1 (+ start of Phase 2) with week-by-week tasks.
Outline:
- Weeks 1–2: Chart factory + metric registry + URL state; shadow-refactor one view (trends.ts) as reference.
- Weeks 3–4: Tooltip system + time comparison primitives; refactor overview + city/revenue-tab.
- Weeks 5–6: Refactor remaining views; ship accessibility + exporting modules; ship methodology page.
- Weeks 7–8: Industry treemap drilldown + seasonality heatmap.
- Weeks 9–10: Contribution endpoint + waterfall in city/report.
- Weeks 11–12: Peer groups scaffolding + percentile badges (start of Phase 3).
- Each week: owner, acceptance criteria, demo script, rollback plan.

### 21.6 `plan/open-questions.md`
Purpose: running log of product/engineering questions + answers.
Outline:
- Seed with the 10 questions in §19.7.
- Table columns: id, area, question, raised_by, target_decision_date, decision, decided_by, notes.
- Process note: new questions added as PR comments and promoted here weekly.

### 21.7 `plan/feature-backlog.md`
Purpose: flat prioritized backlog mirroring §19.1 but sortable and statused.
Outline:
- Columns: id, feature, priority (MUST/SHOULD/NICE), phase, primary_file, blocked_by, estimate (S/M/L/XL), status, owner.
- Sections: Backlog, In-progress, Done, Deferred.
- Links to the relevant section of `docs/visualization-master-plan.md`.

---

## 22. Critical File List

### Files to CREATE (new)
**Frontend charts**
- `frontend/src/charts/factory.ts` — shared chart factory (highest-leverage file in the plan)
- `frontend/src/charts/tooltips.ts` — tooltip formatter library
- `frontend/src/charts/timeComparison.ts` — time-comparison primitives
- `frontend/src/charts/metrics.ts` — metric registry
- `frontend/src/charts/linkedHover.ts` — cross-chart hover sync

**Frontend state & components**
- `frontend/src/state/filters.ts` — URL-backed filter state
- `frontend/src/components/breadcrumb.ts`
- `frontend/src/components/global-filter-bar.ts`
- `frontend/src/components/chart-footer.ts`
- `frontend/src/components/empty-state.ts`
- `frontend/src/components/detail-panel.ts`
- `frontend/src/components/metric-picker.ts`
- `frontend/src/components/onboarding.ts`
- `frontend/src/components/narrative-callouts.ts`
- `frontend/src/data/naics-labels.ts` — build-time NAICS label lookup

**Frontend views**
- `frontend/src/views/methodology.ts`
- `frontend/src/views/dashboard.ts`
- `frontend/src/views/industry.ts`
- `frontend/src/views/seasonality.ts`
- `frontend/src/views/peer-compare.ts`
- `frontend/src/views/pulse.ts`
- `frontend/src/views/watchlist.ts`
- `frontend/src/views/downloads.ts`
- `frontend/src/views/city/industry-detail-panel.ts`
- `frontend/public/maps/ok-counties.topo.json` (bundled asset)

**Backend**
- `backend/app/api/decomposition.py` — contribution endpoint
- `backend/app/api/visualization.py` — heatmap + breadth endpoints
- `backend/app/api/peer_groups.py` — peer-group resolver + rankings
- `backend/app/api/narratives.py` — narrative rules
- `backend/app/services/peer_groups.py`
- `backend/app/services/metrics.py` — HHI, breadth, CV
- `backend/app/services/narratives.py`
- `backend/app/services/chart_pack.py`
- New Alembic migrations:
  - `jurisdiction_peer_groups` table
  - `user_watchlist` table
  - `jurisdiction_events` table
  - `user_profile_preferences.saved_views JSONB` column
  - `contribution_cache` table
  - `mv_peer_group_metrics`, `mv_contribution_yoy`, `mv_breadth` materialized views
  - Revision trigger on `ledger_records` for audit trail

### Files to REFACTOR (existing)
- `frontend/src/main.ts` — register new routes
- `frontend/src/router.ts` — extend for query-param sync
- `frontend/src/paths.ts` — add builders for new routes
- `frontend/src/theme.ts` — import new Highcharts modules; enable accessibility
- `frontend/src/api.ts` — add calls for new endpoints
- `frontend/src/components/sidebar.ts` — 4-group restructure
- `frontend/src/components/chart-controls.ts` — accept `FilterState`
- `frontend/src/components/chart-download.ts` — use Highcharts exporting menu
- `frontend/src/components/kpi-card.ts` — peer percentile chip
- `frontend/src/views/overview.ts`, `trends.ts`, `rankings.ts`, `compare.ts`, `county.ts`, `forecast.ts`, `anomalies.ts`, `missed-filings.ts`, `report.ts` — use `createChart`
- `frontend/src/views/city.ts` + `city/{overview,revenue,industry,seasonality,details}-tab.ts` — use `createChart`; replace manual row-click drilldown with Highcharts drilldown
- `backend/app/db/schema.sql` — new tables, triggers, MVs
- `backend/app/api/cities.py` — wire peer-percentile fields into `/cities/{copo}` response
- `backend/app/api/analytics.py` — add `top_n + remainder` support on rankings

---

## 23. Verification Plan

End-to-end verification for each phase. The implementation agents should treat this as the acceptance spec.

### 23.1 Phase 1 verification
1. `cd frontend && npm run build` — build passes with no new TypeScript errors.
2. `cd backend && python -m unittest discover -s tests -v` — existing tests pass.
3. **Manual (dev stack via `./start.sh`):**
   - Load `/` and confirm chart renders via factory (inspect DOM for `data-chart-id` attribute set by factory).
   - Change tax-type, reload page → filter persists (URL-bound).
   - Click "Copy link" on a chart → pasted URL reloads the exact same state.
   - Click "Export CSV" on statewide trend → CSV downloads.
   - Navigate to `/methodology` → page renders with data source, as-of date, revision policy.
   - Tab through a chart with keyboard → accessibility module responds.
4. **Automated (new — Phase 1 deliverable):** snapshot tests for 10 canonical chart specs using Vitest + a headless Highcharts runner.

### 23.2 Phase 2 verification
1. Navigate to a city industry tab → treemap renders, click NAICS-2 node → drills to NAICS-4, URL updates to `?naics=44`, breadcrumb updates, back button returns.
2. Navigate to city seasonality tab → heatmap renders; hover a cell → subseries chart highlights same month via `linkedHover`.
3. Load `/county/Tulsa` → choropleth renders.
4. On a city overview, click a data point → navigates to `/report/:copo/:year/:month`.
5. `curl /api/stats/contribution?copo=5550&period=2026-04&comparison=YoY&dimension=naics2` returns well-formed JSON with dimensions array.
6. Bundle size check: main chunk <180 KB gzipped; largest per-route chunk <220 KB gzipped.

### 23.3 Phase 3 verification
1. `GET /api/stats/peer-group?copo=5550&type=pop_band` returns peer cities.
2. City overview KPI card shows "#3 of 12 in pop band 10–25k" chip.
3. HHI gauge renders when city has >= 5 NAICS sectors.
4. Anomaly Center v2: click an anomaly → decompose panel opens with waterfall.
5. Peer Compare view renders small multiples for a chosen cohort.
6. Materialized views refreshed nightly; `mv_peer_group_metrics` row count > 0.

### 23.4 Phase 4 verification
1. `GET /api/stats/narratives?copo=5550&period=2026-04` returns ≥1 narrative when rules trigger.
2. Watchlist view persists saved cities across sessions.
3. Chart-pack PDF downloads with 10 charts and preserves captions/filters.
4. Saved views dropdown loads and applies a saved filter state.

### 23.5 Rollback strategy
- Phase 1 refactor is the largest risk. Ship the factory in parallel to existing inline charts, feature-flagged via `?factory=1`; flip default only after snapshot parity on all 10 canonical charts.
- Keep the old `industry-tab.ts` manual drilldown available via `?legacy=1` for two weeks after Phase 2 launch.
- Database migrations are additive only — no destructive drops. New tables and columns can be dropped without affecting existing reads.

---

## Acknowledgements (Current-State Trust)

This plan is grounded in the observed state of the repo on `claude/munirevenue-expansion-plan-5G59s` at 2026-04-12:

- `frontend/src/theme.ts` (Highcharts theme, CVD palette, accessibility disabled at line 49)
- `frontend/src/main.ts` (route registration)
- `frontend/src/router.ts`, `frontend/src/paths.ts`
- `frontend/src/api.ts` (~612 lines — 50+ endpoint wrappers)
- `frontend/src/views/*.ts` (17 views)
- `frontend/src/views/city/*.ts` (5 city tabs)
- `frontend/src/components/*.ts` (7 shared components, incl. `chart-controls.ts`, `kpi-card.ts`)
- `backend/app/api/cities.py` (1841 lines — /cities, /ledger, /naics, /seasonality, /forecast, /anomalies/decompose, /counties/{name}/*)
- `backend/app/api/analytics.py` (1384 lines — /stats/statewide-trend, /rankings, /naics-sectors, /anomalies, /missed-filings)
- `backend/app/services/{forecasting,anomaly_detector,analysis,reporting}.py`
- `backend/app/models/orm.py` (Jurisdiction, LedgerRecord, NaicsRecord, Anomaly, ForecastRun, ...)
- `backend/app/db/schema.sql` (defines `mv_monthly_revenue_by_city`, `mv_top_naics_by_city`, `mv_yoy_comparison`)
- `docs/{architecture,data-model,data-import-guide,api-security,missed-filings-design,hetzner-deployment,seo-ops}.md`

Where the plan uses "NEW," the file does not yet exist. Where it uses "REFACTOR," the file exists and is called out in the critical-file list. Every recommendation traces to at least one of these paths.
