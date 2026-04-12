# MuniRevenue Metrics Dictionary

**Status:** Outline — seed file for implementation agents.
**Companion to:** `docs/visualization-master-plan.md` §8.
**Mirrors:** `frontend/src/charts/metrics.ts` (NEW, not yet created) and `backend/app/services/metrics.py` (NEW).

## Purpose

Single source of truth for every metric rendered in MuniRevenue charts. Each entry gives implementers (frontend + backend) everything they need to compute, label, and caveat a metric without re-deriving it in each view. This dictionary drives both the generic metric-picker component and the backend metrics service.

## Entry schema

Every metric MUST include:

| Field | Description |
|---|---|
| `id` | Stable key used in URL state and registry lookups (e.g. `revenue_t12m`) |
| `label` | Human-readable label ("Trailing 12-month revenue") |
| `short_label` | Compact label for axes/legends ("T12M revenue") |
| `unit` | `usd` \| `pct` \| `ratio` \| `count` \| `index` |
| `formula` | Plain-language formula + SQL reference |
| `source_table` | Source table or materialized view |
| `supported_levels` | Array of `state` / `county` / `city` / `city-industry` / `tax-type` / `peer` |
| `default_viz` | Default chart type id from the catalog |
| `higher_is_better` | `true` / `false` / `null` (for neutral metrics) |
| `comparison_mode_support` | Array of time comparison modes the metric works with |
| `caveats` | Free-text warnings for rendering |
| `example` | One literal example value rendered in chart context |

## Sections (to be filled in during Phase 1)

### 1. Core
- `revenue_monthly`
- `revenue_t3m`
- `revenue_t12m`
- `revenue_per_capita`
- `revenue_by_tax_type`

### 2. Comparative
- `mom_pct`, `mom_abs`
- `yoy_pct`, `yoy_abs`
- `ytd_vs_prior_ytd_pct`
- `vs_peer_median_pct`
- `index_to_100`

### 3. Composition
- `naics_share_of_total`
- `tax_type_share`
- `top_n_concentration`

### 4. Contribution
- `yoy_contribution_abs_by_naics`
- `share_of_total_change`
- `share_gain_loss`

### 5. Volatility
- `coefficient_of_variation_24m`
- `rolling_stdev_12m`
- `max_drawdown_from_peak`

### 6. Peer
- `peer_percentile_rank`
- `peer_median_p25_p75`
- `distance_to_peer_median`

### 7. Concentration
- `hhi_by_naics`
- `top_1_dependency`
- `breadth_of_growth_t12m`
- `gini_by_naics` (nice-to-have)

### 8. Anomaly
- `z_score_vs_expected`
- `missed_filings_estimated_impact`
- `revision_magnitude`

## Derivation notes

- MoM and YoY are already computed in SQL window functions in `backend/app/api/cities.py:685+` (`get_city_ledger`) and `backend/app/api/analytics.py:491+` (`get_statewide_trend`). Metrics dictionary SHOULD cite those SQL blocks by line number to anchor the formula.
- Per-capita is precomputed in `mv_monthly_revenue_by_city.returned_per_capita`.
- NAICS share is precomputed in `mv_top_naics_by_city.pct_of_city_total`.
- HHI, CV, breadth, z-score are NEW — implement in `backend/app/services/metrics.py`.

## Rendering rules

- Delta metrics display warm-orange for negative, teal for positive. Never red/green.
- Currency formatted via existing `formatCurrency()` in `frontend/src/utils.ts`.
- Percentages formatted via `formatPercent()`.
- Suppressed / preliminary states rendered per `visualization-master-plan.md` §12.5.
