# MuniRevenue Visualization — Feature Backlog

**Status:** Outline — seed file for implementation agents.
**Companion to:** `docs/visualization-master-plan.md` §19.1.

## Purpose

Flat, sortable, statusable prioritized backlog. Every feature traces to a phase, a priority, a primary file, and a section of the master plan.

## Schema
| Col | Meaning |
|---|---|
| `id` | Stable ref (F01, F02, ...) |
| `feature` | Plain-language title |
| `priority` | `MUST` / `SHOULD` / `NICE` |
| `phase` | 1–4 |
| `primary_file` | Anchor file or module |
| `blocked_by` | Other feature id, if any |
| `estimate` | S / M / L / XL |
| `status` | `backlog` / `in-progress` / `done` / `deferred` |
| `owner` | TBD |
| `plan_ref` | Section of `visualization-master-plan.md` |

## Backlog

| id | feature | prio | phase | primary_file | blocked_by | est | status | plan_ref |
|---|---|---|---|---|---|---|---|---|
| F01 | Shared chart factory | MUST | 1 | `frontend/src/charts/factory.ts` | — | L | backlog | §11 |
| F02 | URL-backed filter state | MUST | 1 | `frontend/src/state/filters.ts` | — | M | backlog | §5.1 |
| F03 | Tooltip formatter library | MUST | 1 | `frontend/src/charts/tooltips.ts` | F01 | M | backlog | §6 |
| F04 | Time comparison primitives | MUST | 1 | `frontend/src/charts/timeComparison.ts` | — | M | backlog | §7 |
| F05 | Metrics registry | MUST | 1 | `frontend/src/charts/metrics.ts` | — | M | backlog | §8 |
| F06 | Linked chart hover | SHOULD | 1 | `frontend/src/charts/linkedHover.ts` | F01 | S | backlog | §6.2 |
| F07 | Accessibility + exporting modules | MUST | 1 | `frontend/src/theme.ts` | — | S | backlog | §11.1 |
| F08 | Methodology page | MUST | 1 | `frontend/src/views/methodology.ts` | — | M | backlog | §15 |
| F09 | Chart footer component | MUST | 1 | `frontend/src/components/chart-footer.ts` | — | S | backlog | §12.8 |
| F10 | Breadcrumb component | MUST | 1 | `frontend/src/components/breadcrumb.ts` | F02 | S | backlog | §5.2 |
| F11 | Global filter bar | MUST | 1 | `frontend/src/components/global-filter-bar.ts` | F02 | M | backlog | §10.2 |
| F12 | Refactor overview to factory | MUST | 1 | `frontend/src/views/overview.ts` | F01, F03 | M | backlog | §9.1 |
| F13 | Refactor trends to factory | MUST | 1 | `frontend/src/views/trends.ts` | F01, F03 | M | backlog | §9.1 |
| F14 | Refactor rankings to factory | MUST | 1 | `frontend/src/views/rankings.ts` | F01 | M | backlog | §9.1 |
| F15 | Refactor compare to factory | MUST | 1 | `frontend/src/views/compare.ts` | F01 | M | backlog | §9.1 |
| F16 | Refactor city tabs to factory | MUST | 1 | `frontend/src/views/city/*-tab.ts` | F01 | L | backlog | §9.1 |
| F17 | Refactor forecast/report/anomalies/missed-filings/county | MUST | 1 | `frontend/src/views/*.ts` | F01 | L | backlog | §9.1 |
| F18 | Snapshot test harness | MUST | 1 | `frontend/tests/charts/*` (NEW) | F01 | M | backlog | §23.1 |
| F19 | Industry treemap drilldown | MUST | 2 | `frontend/src/views/city/industry-tab.ts` | F01, F17 | L | backlog | §4.3, §5.3 |
| F20 | Seasonality heatmap | MUST | 2 | `frontend/src/views/city/seasonality-tab.ts` | F01 | M | backlog | §4.5 |
| F21 | Contribution endpoint | MUST | 2 | `backend/app/api/decomposition.py` | — | L | backlog | §17.1 |
| F22 | Contribution waterfall charts | MUST | 2 | `frontend/src/views/{city/overview-tab,report,county}.ts` | F21 | M | backlog | §4.2 |
| F23 | Heatmap endpoint | SHOULD | 2 | `backend/app/api/visualization.py` | — | S | backlog | §17.2 |
| F24 | Breadth endpoint | SHOULD | 2 | `backend/app/api/visualization.py` | — | S | backlog | §17.3 |
| F25 | County choropleth | SHOULD | 2 | `frontend/src/views/county.ts` | Q01 | M | backlog | §4.7 |
| F26 | City bubble map | SHOULD | 2 | `frontend/src/views/overview.ts` | Q01 | M | backlog | §4.7 |
| F27 | Slope + dumbbell charts | SHOULD | 2 | `frontend/src/views/{compare,rankings}.ts` | F01 | M | backlog | §4.4 |
| F28 | Industry Explorer page | SHOULD | 2 | `frontend/src/views/industry.ts` | F19 | L | backlog | §9.2 |
| F29 | Seasonal Analysis page | SHOULD | 2 | `frontend/src/views/seasonality.ts` | F20 | L | backlog | §9.2 |
| F30 | Index-to-100 toggle on compare | MUST | 1 | `frontend/src/views/compare.ts` | F04 | S | backlog | §7 |
| F31 | Range selector on trends | SHOULD | 2 | `frontend/src/views/trends.ts` | — | S | backlog | §4.1 |
| F32 | Peer groups table + service | MUST | 3 | `backend/app/services/peer_groups.py` | — | L | backlog | §13 |
| F33 | Peer groups API | MUST | 3 | `backend/app/api/peer_groups.py` | F32 | M | backlog | §17.4–5 |
| F34 | Peer percentile KPI chip | MUST | 3 | `frontend/src/components/kpi-card.ts` | F33 | M | backlog | §13.4 |
| F35 | Peer Compare view | MUST | 3 | `frontend/src/views/peer-compare.ts` | F33 | L | backlog | §9.2 |
| F36 | HHI gauge | SHOULD | 3 | `frontend/src/views/city/overview-tab.ts` | — | S | backlog | §4.8 |
| F37 | Concentration warnings | SHOULD | 3 | `frontend/src/components/narrative-callouts.ts` | F36 | S | backlog | §14.4 |
| F38 | Metrics service (HHI, breadth, CV) | SHOULD | 3 | `backend/app/services/metrics.py` | — | M | backlog | §8 |
| F39 | Anomaly Center v2 | SHOULD | 3 | `frontend/src/views/anomalies.ts` | F22 | L | backlog | §9.1 |
| F40 | Economic Pulse view | SHOULD | 3 | `frontend/src/views/pulse.ts` | — | M | backlog | §9.2 |
| F41 | Narrative rules service | SHOULD | 4 | `backend/app/services/narratives.py` | F32, F38 | L | backlog | §14.1 |
| F42 | Narrative callouts UI | SHOULD | 4 | `frontend/src/components/narrative-callouts.ts` | F41 | M | backlog | §14.1 |
| F43 | Watchlist table + view | SHOULD | 4 | `frontend/src/views/watchlist.ts` + migration | — | M | backlog | §14.7 |
| F44 | Saved views | SHOULD | 4 | `frontend/src/components/global-filter-bar.ts` + migration | F11 | M | backlog | §18 |
| F45 | Download Center | SHOULD | 4 | `frontend/src/views/downloads.ts` | — | M | backlog | §9.2 |
| F46 | Chart pack PDF | SHOULD | 4 | `backend/app/services/chart_pack.py` | F01 | L | backlog | §18 |
| F47 | Event annotations | NICE | 4 | new `jurisdiction_events` table | — | M | backlog | §14.9 |
| F48 | Presentation mode | NICE | 4 | factory extension | F01 | S | backlog | §18 |
| F49 | Explain-this-chart helper | NICE | 4 | `frontend/src/components/chart-help.ts` | — | S | backlog | §14.10 |
| F50 | Dashboard v2 page | SHOULD | 1 | `frontend/src/views/dashboard.ts` | F01 | M | backlog | §9.2 |

## In-progress
_(empty — to be filled as work starts)_

## Done
_(empty)_

## Deferred
_(empty)_

## Estimate legend
- **S** — ≤ 1 day
- **M** — 2–4 days
- **L** — 1–2 weeks
- **XL** — > 2 weeks

## Notes
- F01–F18 are the 90-day critical path; everything else unblocks on them.
- Q01 (county TopoJSON licensing) blocks F25 and F26.
- F32 (peer groups service) unblocks seven Phase 3 features.
