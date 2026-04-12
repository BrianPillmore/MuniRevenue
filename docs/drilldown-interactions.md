# Drill-down & Drill-through Interaction Model

**Status:** Outline — seed file for implementation agents.
**Companion to:** `docs/visualization-master-plan.md` §5.

## Purpose

Concrete map of every click target, its destination, and the state that must be preserved. Any chart, table, map, or KPI card in MuniRevenue that accepts a click MUST be listed here before it ships.

## Navigation model

- **Router:** `frontend/src/router.ts` (History API). Routes registered in `frontend/src/main.ts`.
- **URL state:** parsed by `frontend/src/state/filters.ts` (NEW). Canonical query grammar:
  ```
  ?copo=&county=&tax=&period=&compare=&metric=&naics=&smoothing=&index_base=&peers=&saved=
  ```
- **Breadcrumb:** `frontend/src/components/breadcrumb.ts` (NEW) — each crumb strips finer filters.
- **Back stack:** native browser back MUST restore full state (achieved via `history.pushState` on every filter change).

## Drill-down path matrix

| # | From | Click target | Destination | URL change | In-panel or page-replace | Phase |
|---|---|---|---|---|---|---|
| D1 | State monthly line | Data point | Rankings filtered to that month's movers | `?period=YYYY-MM` | page-replace | 1 |
| D2 | State choropleth | County polygon | County view | `/county/:name` | page-replace | 2 |
| D3 | County monthly line | Data point | County month detail | `?period=YYYY-MM` | in-panel | 2 |
| D4 | County city list | City row | City profile | `/city/:copo` | page-replace | 1 |
| D5 | City revenue tab line | Data point | Monthly executive report | `/report/:copo/:y/:m` | page-replace | 1 |
| D6 | City industry treemap | NAICS-2 tile | Same view, drill to NAICS-4 | `?naics=NN` | in-chart drill | 2 |
| D7 | City industry treemap | NAICS-4 tile | Same view, drill to NAICS-6 | `?naics=NNNN` | in-chart drill | 2 |
| D8 | City industry treemap | NAICS-6 leaf | Industry detail side panel | `?naics=NNNNNN` | in-panel | 2 |
| D9 | Waterfall bar | Contribution bar | Filters treemap + linked line | none (linked state) | in-panel | 2 |
| D10 | Anomaly dot on city line | Point | Decompose panel | `?anomaly=YYYY-MM` | in-panel | 2 |
| D11 | Anomaly Center z-strip | Entry | Decompose panel for that city/date | `?copo=&anomaly=` | in-panel | 3 |
| D12 | Peer slope chart | City line | City profile, same peer cohort | `/city/:copo?peers=<group>` | page-replace | 3 |
| D13 | Statewide sector heatmap | Year/month cell | Drill to month of that sector | `?period=&sector=` | page-replace | 2 |
| D14 | Missed-filings dot | Entry | Missed-filing detail panel | `?copo=&naics=&period=` | in-panel | 2 |
| D15 | KPI card peer chip | Chip | Peer Compare view for this cohort | `/peer-compare?group=&focus=` | page-replace | 3 |

## In-panel vs page-replace rules

- **In-panel** (keep context): industry NAICS-6 detail, anomaly decompose, peer card, revision history, missed-filing detail.
- **Page-replace**: any change of geography (city/county), change of report month, switch to peer-compare view, switch to monthly report.

## Linked hover groups

Registered via `frontend/src/charts/linkedHover.ts`. Groups to seed:

| Group id | Members |
|---|---|
| `city-overview-<copo>` | Main revenue line, YoY bar, KPI sparklines, anomaly line |
| `city-seasonality-<copo>` | Year×month heatmap, seasonal subseries grid, seasonal index line |
| `county-contrib-<county>` | County line, city contribution waterfall, city ranking bar |
| `peer-<group_key>` | All small-multiples peer charts on Peer Compare view |

## Example workflows

1. **Finance director investigates Broken Arrow April drop.** Starts on city overview, sees YoY bar red (warm-orange), clicks it → lands on report page with contribution waterfall → clicks the "Food services" bar → side panel opens with NAICS-6 detail + peer comparison.
2. **Mayor preps council talking points.** Opens city overview → copies link → pastes into email. Recipient lands on the exact same view with filters intact.
3. **Analyst compares 5 tourism cities over 5 years.** Opens Peer Compare → picks tourism-high cohort → switches to index-to-100 mode → saves view → shares link.
4. **Journalist finds fastest-growing city.** Opens Rankings → switches metric to YoY → sorts descending → clicks top result → lands on city profile.
5. **County official decomposes county decline.** Opens County view → waterfall by city → clicks largest declining city → drills to that city's own industry waterfall.
6. **Econ dev officer tracks NAICS 722 share.** Opens Industry Explorer → drills statewide NAICS tree to 722 → city heatmap shows share change across all cities.

## Shareable link format

```
https://munirevenue.com/city/5550?tax=sales&compare=YoY&period=FY2026&metric=revenue_t12m&naics=722&peers=band-25k-50k
```

- URL is the source of truth for filter state.
- `?saved=<id>` resolves to a server-stored view from `user_profile_preferences.saved_views` JSONB.
- Every view MUST round-trip its state through `parseFilters` → `serializeFilters`.
