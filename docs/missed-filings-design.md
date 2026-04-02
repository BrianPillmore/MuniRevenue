# Missed Filings Design

## Goal

Identify likely missed monthly filings for Oklahoma city tax payers by 6-digit NAICS code.

The output is directional. It should tell a city clerk or finance director which industry code to inspect first, not assert that a filing is definitively missing.

## Product Shape

The feature has two distinct layers:

1. A statewide analytical feed of likely missed filings
2. A user workflow layer where authenticated users can save items for follow-up

The analytical feed is public to the product’s protected investigation surface. The follow-up queue is user-specific and stored in account tables.

## Data Window

This is an exhaustive per-NAICS cache for the rolling 24-month product window.

The refresh job materializes every analyzable city, tax type, month, and 6-digit NAICS combination that has enough baseline history to score, and the API then applies the selected run-rate method, materiality thresholds, and severity rules.

## Operating Rules

- scope to the rolling prior 24 months
- limit to `sales` and `use`
- exclude `lodging` because lodging-by-NAICS source files do not exist in the current pipeline
- score only lower-sided anomalies
- require both relative and absolute materiality

## Baseline Methods

Supported run-rate definitions:

- `hybrid`
- `yoy`
- `trailing_mean_3`
- `trailing_mean_6`
- `trailing_mean_12`
- `trailing_median_12`
- `exp_weighted_12`

The hybrid default blends:

- same-month prior year
- trailing 12-month median

That keeps seasonality while staying robust to noisy months.

## Detection Logic

For each city, tax type, month, and 6-digit NAICS code in the 24-month window:

1. Compute the selected baseline run rate
2. Compare actual revenue to expected revenue
3. Compute:
   - `missing_amount`
   - `missing_pct`
   - `baseline_share_pct`
4. Require enough baseline support for the chosen method
5. Require all selected materiality thresholds
6. Assign `medium`, `high`, or `critical` severity

Important detail:

- `baseline_share_pct` is measured against a city-level baseline rather than the already-depressed current month

## Persistence Model

Operational tables:

- `missed_filing_candidates`
- `missed_filing_candidates_refresh_meta`

User follow-up table:

- `user_saved_missed_filings`

That separation matters:

- the cache is analytical and refresh-driven
- the follow-up queue is user-owned and durable across refreshes

## Refresh Model

The refresh process:

- rebuilds the candidate set
- stages the next snapshot
- publishes atomically
- stores refresh metadata for UI/API display

This avoids serving a partially rebuilt live table.

## Why This Model

This design is intentionally:

- explainable
- tunable from the UI
- appropriate for seasonal monthly revenue series
- robust to one-off spikes
- oriented to finance-staff triage rather than black-box alerting

## User Workflow

Authenticated users can:

- view missed-filings candidates
- save a candidate as a follow-up
- manage saved items in the account page
- mark items investigating / resolved / dismissed
- attach notes

This lets the feature become an operational queue instead of a one-time report.

## Research Basis

- Seasonal Hybrid ESD pattern:
  - https://github.com/nachonavarro/seasonal-esd-anomaly-detection
- Microsoft anomaly-detection guidance:
  - https://learn.microsoft.com/en-us/azure/ai-services/anomaly-detector/concepts/anomaly-detection-best-practices
- Statsmodels STL reference:
  - https://www.statsmodels.org/v0.12.2/examples/notebooks/generated/stl_decomposition.html
- NIST MAD guidance:
  - https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/mad.htm
- NIST EWMA guidance:
  - https://www.itl.nist.gov/div898/handbook/mpc/section2/mpc2211.htm
- NIST process monitoring guidance:
  - https://www.itl.nist.gov/div898/handbook/toolaids/pff/pmc.pdf
- Azure Stream Analytics dip-detection reference:
  - https://learn.microsoft.com/en-us/stream-analytics-query/anomalydetection-spikeanddip-azure-stream-analytics
