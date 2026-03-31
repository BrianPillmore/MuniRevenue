/* ══════════════════════════════════════════════
   Formatting utilities
   ══════════════════════════════════════════════ */

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCompactCurrency(value: number): string {
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return formatCurrency(value);
}

export function formatPercent(value: number | null): string {
  return value === null ? "N/A" : `${value.toFixed(2)}%`;
}

export function formatPlain(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(4);
}

export function formatBoolean(value: boolean | null): string {
  if (value === null) return "Unknown";
  return value ? "Yes" : "No";
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function monthName(month: number): string {
  return MONTH_NAMES[(month - 1) % 12] ?? `Month ${month}`;
}

/**
 * Return a trend arrow span with color class.
 * Positive values get green up arrow, negative get red down arrow.
 * Null or zero returns an empty string.
 */
export function trendArrow(value: number | null): string {
  if (value === null || value === 0) return "";
  if (value > 0) {
    return `<span class="trend-up" aria-label="up ${value.toFixed(1)}%">&#8593; ${value.toFixed(1)}%</span>`;
  }
  return `<span class="trend-down" aria-label="down ${Math.abs(value).toFixed(1)}%">&#8595; ${Math.abs(value).toFixed(1)}%</span>`;
}

/**
 * Build a standard HTML table wrapper.
 */
export function wrapTable(headers: string[], body: string): string {
  return `
    <div class="table-shell">
      <table>
        <thead>
          <tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

/* ══════════════════════════════════════════════
   Chart analysis utilities
   ══════════════════════════════════════════════ */

/** Compute rolling average of given window size */
export function rollingAverage(values: number[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    const slice = values.slice(i - window + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

/** Compute seasonal factors from monthly data (12 factors, one per calendar month) */
export function computeSeasonalFactors(dates: string[], values: number[]): number[] {
  const byMonth: number[][] = Array.from({ length: 12 }, () => []);
  dates.forEach((d, i) => {
    const month = new Date(d).getMonth(); // 0-11
    byMonth[month].push(values[i]);
  });
  const overallAvg = values.reduce((a, b) => a + b, 0) / values.length;
  return byMonth.map((arr) =>
    arr.length > 0
      ? arr.reduce((a, b) => a + b, 0) / arr.length / overallAvg
      : 1,
  );
}

/** Apply seasonal adjustment: divide each value by its month's seasonal factor */
export function seasonallyAdjust(
  dates: string[],
  values: number[],
  factors: number[],
): number[] {
  return values.map((v, i) => {
    const month = new Date(dates[i]).getMonth();
    const factor = factors[month] || 1;
    return v / factor;
  });
}

/** Convert values to month-over-month percent change */
export function toPercentChange(values: number[]): (number | null)[] {
  return values.map((v, i) => {
    if (i === 0) return null;
    const prev = values[i - 1];
    if (prev === 0) return null;
    return ((v - prev) / Math.abs(prev)) * 100;
  });
}

/** Compute linear trendline (returns array of y values for the trendline) */
export function linearTrendline(values: number[]): number[] {
  const n = values.length;
  if (n === 0) return [];
  const xMean = (n - 1) / 2;
  const yMean = values.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - xMean) * (values[i] - yMean);
    den += (i - xMean) ** 2;
  }
  const slope = den !== 0 ? num / den : 0;
  const intercept = yMean - slope * xMean;
  return values.map((_, i) => intercept + slope * i);
}
