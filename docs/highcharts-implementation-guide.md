# Highcharts Implementation Guide

**Status:** Outline — seed file for implementation agents.
**Companion to:** `docs/visualization-master-plan.md` §11.

## Purpose

Engineering reference for every Highcharts decision in MuniRevenue. If an engineer is about to call `Highcharts.chart(...)` directly, they should read this first and instead call `createChart()` from the shared factory.

## 1. Module inventory

Current state (`frontend/src/theme.ts`): only `highcharts` core is imported. Accessibility is disabled at line 49.

### Phase 1 additions (MUST)

| Module | Purpose |
|---|---|
| `highcharts/modules/drilldown` | Treemap, bar, and map drilldown |
| `highcharts/modules/treemap` | Industry composition |
| `highcharts/modules/heatmap` | Year × month seasonality |
| `highcharts/highcharts-more` | Waterfall, dumbbell, arearange, solidgauge |
| `highcharts/modules/accessibility` | WCAG compliance |
| `highcharts/modules/exporting` | Export menu |
| `highcharts/modules/offline-exporting` | Client-side PNG/SVG (no server trip) |
| `highcharts/modules/export-data` | CSV download |

### Phase 2 additions (SHOULD)

| Module | Purpose |
|---|---|
| `highcharts/modules/annotations` | Event markers, anomaly callouts |
| `highcharts/modules/stock` | Range selector for long series |
| `highcharts/modules/boost` | Peer scatter, >500 points |
| `highcharts/modules/map` | Choropleth + bubble map |
| `highcharts/modules/pattern-fill` | Prelim/revised shading |

### Dynamic imports

Vite supports dynamic imports natively. Each route MUST dynamic-import only the modules it needs. Treemap and map modules SHOULD NOT be in the main bundle.

## 2. Shared chart factory

### Location
`frontend/src/charts/factory.ts` (NEW)

### API (TypeScript signatures, to be finalized in Phase 1)

```ts
export interface ChartSpec {
  type: ChartType;                // 'line' | 'bar' | 'treemap' | 'heatmap' | 'waterfall' | ...
  level: ChartLevel;              // 'state' | 'county' | 'city' | ...
  data: unknown;                  // normalized data keyed to metric id
  metric: MetricId;               // from metrics registry
  comparison?: ComparisonMode;    // 'none' | 'YoY' | 'MoM' | 'T12M' | 'INDEX_100' | ...
  tooltip?: TooltipFamily;        // 'timeSeries' | 'composition' | 'peer' | 'waterfall' | 'heatmap'
  linkedGroup?: string;
  annotations?: Annotation[];
  drilldown?: DrilldownSpec;
  rangeSelector?: RangeSelectorOptions;
  boost?: boolean;
  exportMenu?: boolean;           // default true
  syncFilter?: FilterSyncSpec;    // write-back filter state on interaction
}

export interface ChartHandle {
  chart: Highcharts.Chart;
  setData(data: unknown): void;
  setComparison(mode: ComparisonMode): void;
  destroy(): void;
}

export function createChart(el: HTMLElement, spec: ChartSpec): ChartHandle;
export function createChartGrid(el: HTMLElement, specs: ChartSpec[]): GridHandle;
export function registerLinkedChartGroup(groupId: string): void;
```

### Factory responsibilities
1. Apply theme from `frontend/src/theme.ts`.
2. Look up metric config from `frontend/src/charts/metrics.ts` (unit, label, higher_is_better).
3. Attach tooltip formatter from `frontend/src/charts/tooltips.ts`.
4. Wire URL sync via `frontend/src/state/filters.ts`.
5. Register with linked-hover group via `frontend/src/charts/linkedHover.ts`.
6. Attach export menu.
7. Apply revision-state markers via `markRevisionState(point)`.
8. Enforce performance budget (boost on scatter > 500 points, lazy load for below-fold charts via `requestIdleCallback`).

## 3. Tooltip formatter library

Location: `frontend/src/charts/tooltips.ts` (NEW)

Exports:
- `timeSeriesTooltip(opts)` — with optional sparkline
- `compositionTooltip(opts)` — treemap, stacked bar
- `peerTooltip(opts)` — scatter, strip, bullet
- `waterfallTooltip(opts)` — contribution bars
- `heatmapTooltip(opts)` — year×month cells

Every formatter accepts an `EnrichedPoint` type with fields like `mom_pct`, `yoy_pct`, `t12m`, `is_preliminary`, `seasonal_index`, `trailing24` (for sparkline).

See `visualization-master-plan.md` §6.5 for the reference formatter pattern.

## 4. Theme extension

Extend `frontend/src/theme.ts`:
- Enable `accessibility: { enabled: true }` (reverse current line 49).
- Add revision-state palette helpers (dashed stroke for preliminary, triangle marker for revised).
- Add `exporting.fallbackToExportServer: false` so no network egress.
- Extend categorical palette with 2 tertiary shades for treemap depth.

## 5. Drilldown patterns

### NAICS tree (Phase 2)
- Use `series.drilldown` with server-side data: each NAICS node pre-emits its children for instant drill.
- Backend endpoint: extend `/api/cities/{copo}/naics` to support `?depth=2|4|6&parent=<code>`.
- URL writeback: drilldown `afterDrilldown` event writes `?naics=<code>` via router.

### City-to-county (Phase 2)
- Drilldown on bar rankings to expand a county into its cities.
- Uses `mv_monthly_revenue_by_city`.

## 6. Reference configs

### Treemap
```
{
  chart: { type: 'treemap' },
  series: [{
    type: 'treemap',
    layoutAlgorithm: 'squarified',
    allowTraversingTree: true,
    alternateStartingDirection: true,
    levels: [
      { level: 1, dataLabels: { enabled: true } },
      { level: 2, dataLabels: { enabled: false } }
    ],
    data: naicsTree
  }]
}
```

### Year × month heatmap
```
{
  chart: { type: 'heatmap' },
  xAxis: { categories: monthLabels },
  yAxis: { categories: years, reversed: true },
  colorAxis: { min: -0.2, max: 0.2, stops: [[0, '#d97a3c'], [0.5, '#f8f6f1'], [1, '#2b7a9e']] },
  series: [{ name: 'YoY', data: cells }]
}
```

### Waterfall (contribution)
```
{
  chart: { type: 'waterfall' },
  xAxis: { type: 'category' },
  series: [{
    upColor: '#2b7a9e',
    color: '#d97a3c',
    data: [
      { name: 'FY25', y: 1234567 },
      { name: 'Food services', y: 20000 },
      { name: 'General retail', y: -35000 },
      ...
      { name: 'FY26', isSum: true, color: '#1b3a5c' }
    ]
  }]
}
```

### Boost scatter
```
{
  chart: { type: 'scatter' },
  boost: { useGPUTranslations: true, usePreallocated: true },
  series: [{ data: allCities, turboThreshold: 0 }]
}
```

### Stock range selector
```
Highcharts.stockChart(el, {
  rangeSelector: { buttons: [
    { type: 'year', count: 1, text: '1Y' },
    { type: 'year', count: 3, text: '3Y' },
    { type: 'year', count: 5, text: '5Y' },
    { type: 'year', count: 10, text: '10Y' },
    { type: 'all', text: 'All' }
  ], selected: 3 },
  series: [{ type: 'line', data: state120m }]
})
```

## 7. Accessibility checklist
- [ ] Import `highcharts/modules/accessibility` in `theme.ts`.
- [ ] Set `accessibility.enabled: true`.
- [ ] Every chart produced by factory has a `description` derived from metric label + period.
- [ ] Keyboard navigation enabled for drilldown.
- [ ] Color contrast ≥ 4.5:1 for text and icons.
- [ ] Tab order follows visual order.

## 8. Export menu configuration

```
exporting: {
  enabled: true,
  fallbackToExportServer: false,
  buttons: {
    contextButton: {
      menuItems: ['downloadPNG','downloadSVG','downloadCSV','downloadXLS','separator','printChart']
    }
  }
}
```

Copy-link button SHOULD live outside Highcharts in `frontend/src/components/chart-download.ts`.

## 9. Linked hover

```
// frontend/src/charts/linkedHover.ts
export function registerLinkedChart(chart: Highcharts.Chart, groupId: string) { ... }
// Listens to point.mouseOver, dispatches CustomEvent('chart:hover', {...})
// All charts sharing groupId call chart.series[0].points[i].onMouseOver() on match
```

## 10. Performance budget
- Main bundle ≤ 180 KB gzipped.
- Largest per-route chunk ≤ 220 KB gzipped.
- Time-to-first-chart < 1.5 s on a cold load on 3G Fast.
- Scatter charts use `boost` when point count > 500.
- Treemap with > 500 leaves triggers drilldown-only rendering (no flat view).

## 11. Testing patterns
- **Snapshot tests** for 10 canonical chart specs (Vitest + jsdom).
- **Visual regression** via Playwright screenshots on the 10 canonical specs.
- **Drilldown tests**: automated click sequence that verifies URL, breadcrumb, and data update.
- **Tooltip tests**: assert enriched-point fields present in formatter output.

## 12. Refactor order (Phase 1)
1. `frontend/src/views/trends.ts` (reference impl)
2. `frontend/src/views/overview.ts`
3. `frontend/src/views/city/revenue-tab.ts`
4. `frontend/src/views/rankings.ts`
5. `frontend/src/views/compare.ts`
6. `frontend/src/views/county.ts`
7. `frontend/src/views/forecast.ts`
8. `frontend/src/views/anomalies.ts`
9. `frontend/src/views/missed-filings.ts`
10. `frontend/src/views/report.ts`
11. `frontend/src/views/city/{overview,industry,seasonality,details}-tab.ts`

Feature-flag via `?factory=1` in development. Flip default only after snapshot parity.
