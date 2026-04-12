# MuniRevenue 90-Day Rollout Plan

**Status:** Outline — seed file for implementation agents.
**Companion to:** `docs/visualization-master-plan.md` §16 (Phase 1 + early Phase 2).

## Purpose

Operationalize the first 12 weeks of the visualization expansion. Each week has a goal, the files touched, the owner slot, acceptance criteria, a demo script, and a rollback plan. Every item maps to a row in `plan/feature-backlog.md`.

## Guiding principles
- Ship the shared chart factory BEFORE any new chart types land.
- Ship URL-backed filter state in the same phase as the factory — they reinforce each other.
- Feature-flag the factory via `?factory=1` until parity is reached on all 10 canonical chart specs.
- Migrations are additive only. No destructive schema changes in 90 days.

## Week-by-week

### Weeks 1–2 — Foundation scaffolding
**Goals:**
- Create `frontend/src/charts/{factory.ts, metrics.ts, tooltips.ts, timeComparison.ts, linkedHover.ts}` as skeletons.
- Create `frontend/src/state/filters.ts` with URL parser + serializer.
- Create snapshot test harness.
- Shadow-refactor `frontend/src/views/trends.ts` as the reference implementation.

**Acceptance:** trends view renders identically whether `?factory=1` or not; snapshot test passes.
**Demo script:** open `/trends`, toggle factory flag, confirm pixel parity.
**Rollback:** delete `frontend/src/charts/` and revert `trends.ts` — no DB changes.

### Weeks 3–4 — Tooltip system + time comparison
**Goals:**
- Implement `timeSeriesTooltip`, `compositionTooltip`, `peerTooltip`, `waterfallTooltip`, `heatmapTooltip` in `tooltips.ts`.
- Implement `toT12M`, `toT3M`, `toYoYDelta`, `toIndex100`, `toYTD`, `toSeasonalIndex` in `timeComparison.ts`.
- Refactor `frontend/src/views/overview.ts` and `frontend/src/views/city/revenue-tab.ts` onto factory.

**Acceptance:** enriched tooltips live on overview + city revenue; T12M and index-to-100 toggles wired to URL.
**Demo script:** toggle T12M on city revenue; confirm tooltip shows MoM/YoY/T12M/seasonal index; reload to confirm URL persistence.

### Weeks 5–6 — Accessibility, exporting, methodology, remaining refactor
**Goals:**
- Import `highcharts/modules/{accessibility, exporting, offline-exporting, export-data}` in `theme.ts`.
- Enable `accessibility: { enabled: true }`.
- Refactor `rankings.ts`, `compare.ts`, `county.ts`, `forecast.ts`, `anomalies.ts`, `missed-filings.ts`, `report.ts` onto factory.
- Create `frontend/src/views/methodology.ts` (NEW page).
- Create `frontend/src/components/{chart-footer.ts, breadcrumb.ts, global-filter-bar.ts, empty-state.ts}`.

**Acceptance:** all existing views use factory; every chart has export menu; methodology page live; copy-link button ships on every chart.
**Demo script:** open any chart, export PNG and CSV; copy link, paste in new tab, confirm same state; tab-navigate a chart with keyboard.

### Weeks 7–8 — Industry treemap + seasonality heatmap
**Goals:**
- Add `drilldown, treemap, heatmap, highcharts-more` modules (dynamic import per route).
- Rewrite `frontend/src/views/city/industry-tab.ts` with treemap drilldown 2→4→6.
- Rewrite `frontend/src/views/city/seasonality-tab.ts` with year×month heatmap + subseries grid.
- Extend `backend/app/api/cities.py` `/cities/{copo}/naics` with `?depth=&parent=` params for drill.

**Acceptance:** click NAICS-2 tile drills to NAICS-4; NAICS-6 opens side panel; heatmap replaces boxplot as default seasonality view.
**Demo script:** open Broken Arrow industry tab; drill 44 → 4451 → 445110; open side panel.
**Rollback:** keep manual row-click behavior behind `?legacy=1`.

### Weeks 9–10 — Contribution endpoint + waterfall
**Goals:**
- Create `backend/app/api/decomposition.py` with `GET /api/stats/contribution`.
- Add `contribution_cache` table (additive migration).
- Add waterfall chart to city overview, county view, and report page.
- Add `backend/app/api/visualization.py` with `GET /api/stats/heatmap`.

**Acceptance:** report page shows a YoY waterfall for the selected month; API returns JSON shape per `visualization-master-plan.md` §17.1.
**Demo script:** open a city report, confirm waterfall, click a contribution bar, see linked treemap filter.

### Weeks 11–12 — Peer groups scaffolding (start of Phase 3)
**Goals:**
- Create `jurisdiction_peer_groups` table (additive migration).
- Create `backend/app/services/peer_groups.py` with `build_pop_band_groups`, `build_metro_adjacency`, `build_tax_base_size`.
- Create `backend/app/api/peer_groups.py` with `GET /api/stats/peer-group` and `GET /api/stats/peer-group/{group_key}/rankings`.
- Wire peer percentile chip into `frontend/src/components/kpi-card.ts`.
- Schedule nightly job to rebuild peer groups.

**Acceptance:** city overview shows "#3 of 12 in pop band 10–25k" chip; API returns peer lists.
**Demo script:** open Edmond overview, click peer chip, land on Peer Compare view.

## Cross-cutting

### Testing
- Snapshot tests for 10 canonical chart specs — ship Week 1, maintain throughout.
- Visual regression (Playwright) starts Week 5.
- Backend unit tests for new endpoints as they land.

### Performance budget
- Main bundle ≤ 180 KB gzipped by Week 6.
- Per-route chunks ≤ 220 KB gzipped by Week 8.
- Enforce via Vite build size check in CI.

### Observability
- Add a lightweight `chart:render` event log in factory to track load times in dev.

## Owners (to be assigned)
- Frontend lead: charts/factory, tooltips, timeComparison, view refactors
- Backend lead: decomposition, peer_groups, metrics service
- Designer: tooltip specs, revision markers, methodology page layout
- QA: snapshot + visual regression harness

## Demos
- Weekly Friday demo cadence.
- Weeks 2, 4, 6: internal-only.
- Weeks 8, 10, 12: stakeholder demos (founder + design partners).
