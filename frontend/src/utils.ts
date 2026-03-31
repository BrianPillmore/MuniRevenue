/* ══════════════════════════════════════════════
   Formatting utilities
   ══════════════════════════════════════════════ */

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
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
