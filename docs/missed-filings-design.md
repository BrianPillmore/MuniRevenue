# Missed Filings Design

## Goal

Identify likely missed monthly filings for Oklahoma city tax payers by 6-digit NAICS code. The output is directional: it should tell a city clerk or finance director which industry code to inspect first, not assert that a filing is definitively missing.

This is an exhaustive per-NAICS cache for the rolling 24-month product window, not a rank-limited heuristic shortlist. The refresh job materializes every analyzable city, tax type, month, and 6-digit NAICS combination that has enough baseline history to score, and the API then applies the selected run-rate method, materiality thresholds, and severity rules.

## Operating Rules

- Scope the feed to the rolling prior 24 months.
- Limit the feed to `sales` and `use` tax.
  Lodging is excluded because the current NAICS pipeline does not include lodging-by-NAICS source files.
- Score only lower-sided anomalies.
  The problem is not “unexpectedly high revenue”, but “expected revenue missing this month”.
- Require both relative and absolute materiality.
  Small dollar dips and tiny-share industries should not crowd the queue.

## Baseline Methods

The endpoint supports multiple run-rate definitions so users can choose how conservative they want the detector to be:

- `hybrid`
  Default. Blend same-month prior year with the trailing 12-month median.
- `yoy`
  Same month prior year only.
- `trailing_mean_3`
  Trailing 3-month average.
- `trailing_mean_6`
  Trailing 6-month average.
- `trailing_mean_12`
  Trailing 12-month average.
- `trailing_median_12`
  Trailing 12-month median.
- `exp_weighted_12`
  Exponentially weighted 12-month average.

The hybrid default exists because same-month prior year preserves seasonality, while a trailing median is more robust to one-off spikes and noisy months.

## Detection Logic

For each city, tax type, month, and 6-digit NAICS code in the 24-month window:

1. Compute the selected baseline run rate.
2. Compare current month actual revenue to expected revenue.
3. Compute:
   - `missing_amount`
   - `missing_pct`
   - `baseline_share_pct`, measured against a city-level run-rate baseline rather than the already-depressed current month
4. Keep only rows that have enough baseline support to score:
   - same month prior year, or
   - at least 2 trailing months for the 3-month mean, or
   - at least 3 trailing months for the 6-month mean, or
   - at least 6 trailing months for the 12-month mean, 12-month median, and exponentially weighted average
5. Keep only candidates that clear:
   - minimum expected dollar size
   - minimum missing dollars
   - minimum missing percent
   - minimum share of the city tax base
6. Assign `medium`, `high`, or `critical` severity from explicit dollar and percent thresholds.

## Why This Model

This design is intentionally simple, explainable, and adjustable from the UI:

- Seasonal baselines matter for revenue series.
- Robust estimators matter because single months can be noisy.
- Lower-sided detection should be tunable separately from generic anomaly feeds.
- Finance staff need transparent scoring inputs, not a black-box flag.
- Materiality should be relative to the city's expected tax base for the month, so a bad month does not artificially inflate industry share.
- The refresh should publish atomically so the live table is either the previous full snapshot or the next full snapshot, never a truncated in-between state.

## Research Basis

- Twitter’s Seasonal Hybrid ESD work is a widely used pattern for seasonal anomaly detection in operational time series.
  https://github.com/nachonavarro/seasonal-esd-anomaly-detection
- Microsoft’s anomaly-detection guidance emphasizes seasonal windows, enough historical periods, and separate handling for latest-point monitoring.
  https://learn.microsoft.com/en-us/azure/ai-services/anomaly-detector/concepts/anomaly-detection-best-practices
- Statsmodels STL documentation is the canonical reference for decomposing monthly series into seasonal and trend components.
  https://www.statsmodels.org/v0.12.2/examples/notebooks/generated/stl_decomposition.html
- NIST documents MAD as a robust alternative to standard deviation for scale and outlier work.
  https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/mad.htm
- NIST documents EWMA as a better fit than Shewhart-style limits for detecting smaller, sustained shifts over time.
  https://www.itl.nist.gov/div898/handbook/mpc/section2/mpc2211.htm
- NIST process monitoring guidance also emphasizes CUSUM and EWMA for smaller sustained shifts, which maps better to missing-filing dips than one-shot spike detection.
  https://www.itl.nist.gov/div898/handbook/toolaids/pff/pmc.pdf
- Azure Stream Analytics exposes lower-sided dip detection as a first-class anomaly mode, which matches this use case better than symmetric spike detection.
  https://learn.microsoft.com/en-us/stream-analytics-query/anomalydetection-spikeanddip-azure-stream-analytics
