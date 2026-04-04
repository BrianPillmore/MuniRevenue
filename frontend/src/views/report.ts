/*
   Monthly Report Page — /report/:copo/:year/:month
   One jurisdiction · One month · Full picture
   ══════════════════════════════════════════════ */

import Highcharts from "highcharts";
import { getMonthlyReport } from "../api";
import { showLoading } from "../components/loading";
import { cityPath, ROUTES } from "../paths";
import { setPageMetadata } from "../seo";
import type {
  AnomalyRow,
  MissedFilingRow,
  MonthlyReportResponse,
  NaicsIndustryRow,
  TaxTypeRevenue,
  TrendPoint,
  View,
  YoyRow,
} from "../types";
import { escapeHtml, formatCurrency } from "../utils";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const TAX_TYPE_LABELS: Record<string, string> = {
  sales: "Sales Tax",
  use: "Use Tax",
  lodging: "Lodging Tax",
};

function taxLabel(t: string): string {
  return TAX_TYPE_LABELS[t] ?? (t.charAt(0).toUpperCase() + t.slice(1) + " Tax");
}

function severityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical": return "#c62828";
    case "high":     return "#e65100";
    default:         return "#f9a825";
  }
}

function severityBg(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical": return "rgba(198,40,40,0.10)";
    case "high":     return "rgba(230,81,0,0.09)";
    default:         return "rgba(249,168,37,0.10)";
  }
}

function severityBadge(severity: string): string {
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);
  const color = severityColor(severity);
  const bg = severityBg(severity);
  return `<span style="background:${bg};color:${color};padding:2px 10px;border-radius:4px;font-size:0.76rem;font-weight:700;">${label}</span>`;
}

function yoyArrow(pct: number | null): string {
  if (pct === null) return "";
  const sign = pct >= 0 ? "▲" : "▼";
  const color = pct >= 0 ? "#2e7d32" : "#c62828";
  return `<span style="color:${color};font-weight:700;">${sign} ${Math.abs(pct).toFixed(1)}%</span>`;
}

function formatPct(value: number | null): string {
  if (value === null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

// ── Revenue summary cards ──────────────────────────────────────────────────

function renderRevenueCards(revenue: TaxTypeRevenue[]): string {
  const filled = revenue.filter((r) => r.actual !== null);
  if (!filled.length) {
    return `<p class="body-copy" style="color:#5c6578;">No revenue data available for this period.</p>`;
  }

  const cards = filled.map((r) => {
    const actual = r.actual ?? 0;
    const forecast = r.forecast;
    const prior = r.prior_year_actual;

    let vsforecast = "";
    if (forecast !== null) {
      const diff = actual - forecast;
      const pct = forecast !== 0 ? (diff / Math.abs(forecast)) * 100 : 0;
      const sign = pct >= 0 ? "+" : "";
      const color = pct >= 0 ? "#2e7d32" : "#c62828";
      vsforecast = `
        <div style="font-size:0.82rem;color:#5c6578;margin-top:4px;">
          Forecast: ${formatCurrency(forecast)}
          <span style="color:${color};font-weight:600;margin-left:6px;">${sign}${pct.toFixed(1)}% vs forecast</span>
        </div>`;
    }

    let vsyoy = "";
    if (prior !== null) {
      const pct = prior !== 0 ? ((actual - prior) / Math.abs(prior)) * 100 : 0;
      const sign = pct >= 0 ? "+" : "";
      const color = pct >= 0 ? "#2e7d32" : "#c62828";
      vsyoy = `
        <div style="font-size:0.82rem;color:#5c6578;margin-top:2px;">
          Prior year: ${formatCurrency(prior)}
          <span style="color:${color};font-weight:600;margin-left:6px;">${sign}${pct.toFixed(1)}% YoY</span>
        </div>`;
    }

    return `
      <div class="panel" style="padding:20px 24px;flex:1;min-width:220px;">
        <p class="eyebrow" style="margin:0 0 4px;">${escapeHtml(taxLabel(r.tax_type))}</p>
        <p style="font-size:1.8rem;font-weight:700;margin:0;color:#1b3a5c;">${formatCurrency(actual)}</p>
        ${vsforecast}
        ${vsyoy}
      </div>
    `;
  }).join("");

  return `<div style="display:flex;gap:16px;flex-wrap:wrap;">${cards}</div>`;
}

// ── Missed filings table ───────────────────────────────────────────────────

function renderMissedFilings(items: MissedFilingRow[]): string {
  if (!items.length) {
    return `<p class="body-copy" style="color:#5c6578;">No missed filing candidates for this period.</p>`;
  }

  const rows = items.map((r) => `
    <tr>
      <td style="padding:10px 12px;font-size:0.85rem;">${severityBadge(r.severity)}</td>
      <td style="padding:10px 12px;font-size:0.85rem;font-weight:600;">${escapeHtml(r.activity_code)}</td>
      <td style="padding:10px 12px;font-size:0.85rem;">${escapeHtml(r.activity_description ?? "—")}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;">${formatCurrency(r.estimated_monthly_value)}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;color:#c62828;font-weight:600;">${formatCurrency(r.missing_amount)}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;">${r.missing_pct.toFixed(1)}%</td>
    </tr>
  `).join("");

  return `
    <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="border-bottom:2px solid var(--line);">
            <th style="padding:8px 12px;text-align:left;font-size:0.78rem;color:#5c6578;font-weight:600;">SEVERITY</th>
            <th style="padding:8px 12px;text-align:left;font-size:0.78rem;color:#5c6578;font-weight:600;">NAICS</th>
            <th style="padding:8px 12px;text-align:left;font-size:0.78rem;color:#5c6578;font-weight:600;">INDUSTRY</th>
            <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">EST. VALUE</th>
            <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">GAP $</th>
            <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">GAP %</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

// ── Anomalies list ─────────────────────────────────────────────────────────

function renderAnomalies(items: AnomalyRow[]): string {
  if (!items.length) {
    return `<p class="body-copy" style="color:#5c6578;">No anomalies flagged for this period.</p>`;
  }

  return items.map((a) => {
    const devSign = a.deviation_pct >= 0 ? "+" : "";
    const devColor = a.deviation_pct >= 0 ? "#2e7d32" : "#c62828";

    return `
      <div class="panel" style="padding:16px 20px;margin-bottom:10px;border-left:4px solid ${severityColor(a.severity)};">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          ${severityBadge(a.severity)}
          <span style="font-size:0.82rem;color:#5c6578;">${escapeHtml(taxLabel(a.tax_type))}</span>
          <span style="font-size:0.82rem;color:#5c6578;">·</span>
          <span style="font-size:0.82rem;color:#5c6578;">${escapeHtml(a.anomaly_type.replace(/_/g, " "))}</span>
          <span style="margin-left:auto;font-size:0.85rem;font-weight:700;color:${devColor};">${devSign}${a.deviation_pct.toFixed(1)}%</span>
        </div>
        <p class="body-copy" style="margin:0 0 6px;">${escapeHtml(a.description)}</p>
        <div style="display:flex;gap:16px;font-size:0.82rem;color:#5c6578;">
          ${a.expected_value !== null ? `<span>Expected: ${formatCurrency(a.expected_value)}</span>` : ""}
          ${a.actual_value !== null ? `<span>Actual: ${formatCurrency(a.actual_value)}</span>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

// ── NAICS industries Highcharts bar ────────────────────────────────────────

function renderNaicsChart(
  container: HTMLElement,
  industries: NaicsIndustryRow[],
  periodLabel: string,
  year: number,
): void {
  const chartEl = container.querySelector<HTMLElement>("#report-naics-chart");
  if (!chartEl || !industries.length) return;

  const categories = industries.map(
    (r) => r.activity_description?.substring(0, 40) ?? r.activity_code,
  );
  const currentData = industries.map((r) => r.current_month);
  const priorData = industries.map((r) => r.prior_year_month ?? 0);

  Highcharts.chart(chartEl, {
    chart: { type: "bar", height: Math.max(300, industries.length * 44) },
    title: { text: "" },
    xAxis: {
      categories,
      title: { text: null },
      labels: { style: { fontSize: "11px" } },
    },
    yAxis: {
      min: 0,
      title: { text: "Revenue ($)" },
      labels: {
        formatter() {
          const v = this.value as number;
          if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
          if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
          return `$${v}`;
        },
      },
    },
    tooltip: {
      formatter() {
        const v = this.y as number;
        const label = v >= 1_000_000
          ? `$${(v / 1_000_000).toFixed(2)}M`
          : v >= 1_000
          ? `$${(v / 1_000).toFixed(0)}K`
          : `$${v.toLocaleString()}`;
        return `<b>${this.series.name}</b><br/>${this.x}: ${label}`;
      },
    },
    legend: { enabled: true },
    plotOptions: { bar: { dataLabels: { enabled: false } } },
    series: [
      {
        type: "bar",
        name: periodLabel,
        data: currentData,
        color: "#1b3a5c",
      },
      {
        type: "bar",
        name: `${String(year - 1)} (prior year)`,
        data: priorData,
        color: "rgba(43,122,158,0.4)",
      },
    ],
    credits: { enabled: false },
  } as Highcharts.Options);
}

// ── 12-month trend Highcharts line ─────────────────────────────────────────

function renderTrendChart(
  container: HTMLElement,
  trend: TrendPoint[],
  highlightYear: number,
  highlightMonth: number,
): void {
  const chartEl = container.querySelector<HTMLElement>("#report-trend-chart");
  if (!chartEl || !trend.length) return;

  const categories = trend.map(
    (p) => `${MONTH_NAMES[p.month - 1]}-${String(p.year).slice(2)}`,
  );
  const actuals = trend.map((p) => p.actual);
  const forecasts = trend.map((p) => p.forecast ?? null);

  const highlightIdx = trend.findIndex(
    (p) => p.year === highlightYear && p.month === highlightMonth,
  );

  const plotBands: Highcharts.XAxisPlotBandsOptions[] = highlightIdx >= 0
    ? [{
        from: highlightIdx - 0.5,
        to: highlightIdx + 0.5,
        color: "rgba(27,58,92,0.06)",
        label: { text: "This month", style: { fontSize: "11px", color: "#1b3a5c" } },
      }]
    : [];

  Highcharts.chart(chartEl, {
    chart: { type: "line", height: 320 },
    title: { text: "" },
    xAxis: {
      categories,
      plotBands,
      labels: { style: { fontSize: "11px" } },
    },
    yAxis: {
      min: 0,
      title: { text: "Sales Tax Revenue ($)" },
      labels: {
        formatter() {
          const v = this.value as number;
          if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
          if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
          return `$${v}`;
        },
      },
    },
    tooltip: {
      shared: true,
      formatter() {
        const pts = this.points ?? [];
        const lines = pts.map((pt) => {
          const v = pt.y as number;
          const label = v >= 1_000_000
            ? `$${(v / 1_000_000).toFixed(2)}M`
            : v >= 1_000
            ? `$${(v / 1_000).toFixed(0)}K`
            : `$${v.toLocaleString()}`;
          return `<span style="color:${pt.series.color}">\u25CF</span> ${pt.series.name}: <b>${label}</b>`;
        });
        return `<b>${this.x}</b><br/>${lines.join("<br/>")}`;
      },
    },
    series: [
      {
        type: "line",
        name: "Actual",
        data: actuals,
        color: "#1b3a5c",
        lineWidth: 2.5,
        marker: { radius: 4 },
      },
      {
        type: "line",
        name: "Forecast",
        data: forecasts,
        color: "#2b7a9e",
        dashStyle: "ShortDash",
        lineWidth: 1.5,
        marker: { radius: 3 },
      },
    ],
    credits: { enabled: false },
    legend: { enabled: true },
  } as Highcharts.Options);
}

// ── YoY table ──────────────────────────────────────────────────────────────

function renderYoyTable(yoy: YoyRow[], year: number): string {
  if (!yoy.length) return "";

  const rows = yoy.map((r) => `
    <tr style="border-bottom:1px solid var(--line);">
      <td style="padding:10px 12px;font-size:0.85rem;font-weight:600;">${escapeHtml(taxLabel(r.tax_type))}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;">${r.current_year !== null ? formatCurrency(r.current_year) : "—"}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;color:#5c6578;">${r.prior_year !== null ? formatCurrency(r.prior_year) : "—"}</td>
      <td style="padding:10px 12px;font-size:0.85rem;text-align:right;">${yoyArrow(r.yoy_pct)} ${r.yoy_pct !== null ? formatPct(r.yoy_pct) : "—"}</td>
    </tr>
  `).join("");

  return `
    <table style="width:100%;border-collapse:collapse;max-width:600px;">
      <thead>
        <tr style="border-bottom:2px solid var(--line);">
          <th style="padding:8px 12px;text-align:left;font-size:0.78rem;color:#5c6578;font-weight:600;">TAX TYPE</th>
          <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">${year}</th>
          <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">${year - 1}</th>
          <th style="padding:8px 12px;text-align:right;font-size:0.78rem;color:#5c6578;font-weight:600;">YoY</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ── Main view ──────────────────────────────────────────────────────────────

function renderReport(container: HTMLElement, data: MonthlyReportResponse): void {
  const pop = data.population
    ? `Pop. ${data.population.toLocaleString()}`
    : "";

  const hasMissed = data.missed_filing_count > 0;
  const hasAnomalies = data.anomaly_count > 0;
  const hasNaics = data.naics_top_industries.length > 0;
  const hasTrend = data.trend_12mo.length > 0;

  const missedBadge = hasMissed
    ? `<span style="background:#c62828;color:#fff;border-radius:12px;padding:1px 10px;font-size:0.82rem;font-weight:700;margin-left:10px;">${data.missed_filing_count}</span>`
    : `<span style="background:rgba(46,125,50,0.12);color:#2e7d32;border-radius:12px;padding:1px 10px;font-size:0.82rem;font-weight:700;margin-left:10px;">None</span>`;

  const anomalyBadge = hasAnomalies
    ? `<span style="background:#e65100;color:#fff;border-radius:12px;padding:1px 10px;font-size:0.82rem;font-weight:700;margin-left:10px;">${data.anomaly_count}</span>`
    : `<span style="background:rgba(46,125,50,0.12);color:#2e7d32;border-radius:12px;padding:1px 10px;font-size:0.82rem;font-weight:700;margin-left:10px;">None</span>`;

  container.innerHTML = `
    <div style="max-width:1000px;margin:0 auto;padding:24px 16px 60px;">

      <!-- ── 1. Header ── -->
      <div class="panel" style="padding:28px 32px;margin-bottom:20px;">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;">
          <div>
            <p class="eyebrow" style="margin:0 0 4px;">Monthly Revenue Report</p>
            <h1 style="font-size:1.9rem;font-weight:800;color:#1b3a5c;margin:0 0 6px;">
              ${escapeHtml(data.city_name)}
            </h1>
            <p style="font-size:1.1rem;color:#5c6578;margin:0;">
              ${escapeHtml(data.period_label)}
              ${data.county_name ? ` · ${escapeHtml(data.county_name)} County` : ""}
              ${pop ? ` · ${pop}` : ""}
            </p>
          </div>
          <a href="${cityPath(data.copo)}" class="button button-ghost" style="font-size:0.85rem;">
            Full City Dashboard →
          </a>
        </div>
      </div>

      <!-- ── 2. Revenue summary ── -->
      <div style="margin-bottom:20px;">
        <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0 0 12px;padding-left:2px;">
          Revenue Summary
        </h2>
        <div id="report-revenue-cards">
          ${renderRevenueCards(data.revenue_by_tax_type)}
        </div>
      </div>

      <!-- ── 3. Missed filings ── -->
      <div class="panel" style="padding:24px 28px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;margin-bottom:16px;">
          <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0;">Missed Filings</h2>
          ${missedBadge}
        </div>
        ${hasMissed
          ? `<p class="body-copy" style="margin:0 0 16px;color:#5c6578;font-size:0.85rem;">
               Businesses that filed in prior periods but have no record for this month.
               Contact the Oklahoma Tax Commission to investigate.
             </p>`
          : ""
        }
        <div id="report-missed-filings">
          ${renderMissedFilings(data.missed_filings)}
        </div>
      </div>

      <!-- ── 4. Anomalies ── -->
      <div class="panel" style="padding:24px 28px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;margin-bottom:16px;">
          <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0;">Revenue Anomalies</h2>
          ${anomalyBadge}
        </div>
        ${hasAnomalies
          ? `<p class="body-copy" style="margin:0 0 16px;color:#5c6578;font-size:0.85rem;">
               Revenue deviations from statistical baselines. Higher deviation % warrants closer review.
             </p>`
          : ""
        }
        <div id="report-anomalies">
          ${renderAnomalies(data.anomalies)}
        </div>
      </div>

      <!-- ── 5. NAICS industry breakdown ── -->
      ${hasNaics ? `
      <div class="panel" style="padding:24px 28px;margin-bottom:20px;">
        <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0 0 4px;">Industry Breakdown</h2>
        <p class="body-copy" style="margin:0 0 16px;color:#5c6578;font-size:0.85rem;">
          Top 10 NAICS industries by sales tax revenue — current month vs. prior year same month.
        </p>
        <div id="report-naics-chart"></div>
      </div>
      ` : ""}

      <!-- ── 6. 12-month trend ── -->
      ${hasTrend ? `
      <div class="panel" style="padding:24px 28px;margin-bottom:20px;">
        <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0 0 4px;">12-Month Sales Tax Trend</h2>
        <p class="body-copy" style="margin:0 0 16px;color:#5c6578;font-size:0.85rem;">
          Actual revenue with forecast overlay. Current month highlighted.
        </p>
        <div id="report-trend-chart"></div>
      </div>
      ` : ""}

      <!-- ── 7. YoY comparison ── -->
      <div class="panel" style="padding:24px 28px;margin-bottom:20px;">
        <h2 style="font-size:1.05rem;font-weight:700;color:#1b3a5c;margin:0 0 16px;">Year-over-Year Comparison</h2>
        ${renderYoyTable(data.yoy_by_tax_type, data.year)}
      </div>

      <!-- ── 8. Footer ── -->
      <div style="text-align:center;padding:20px 0 0;color:#9aa5b4;font-size:0.78rem;">
        Data sourced from OkTAP (Oklahoma Taxpayer Access Point) · oktap.tax.ok.gov
        ${data.latest_data_date ? ` · Latest import: ${data.latest_data_date}` : ""}
        <br/>
        <a href="${ROUTES.about}" style="color:#9aa5b4;text-decoration:underline;font-size:0.78rem;">About MuniRev</a>
      </div>

    </div>
  `;

  // Render Highcharts after DOM is ready
  if (hasNaics) {
    renderNaicsChart(container, data.naics_top_industries, data.period_label, data.year);
  }
  if (hasTrend) {
    renderTrendChart(container, data.trend_12mo, data.year, data.month);
  }
}

// ── View export ────────────────────────────────────────────────────────────

export const reportView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    const { copo, year: yearStr, month: monthStr } = params;
    const year = Number.parseInt(yearStr ?? "", 10);
    const month = Number.parseInt(monthStr ?? "", 10);

    if (!copo || Number.isNaN(year) || Number.isNaN(month)) {
      container.innerHTML = `
        <div style="padding:40px;text-align:center;">
          <p class="body-copy" style="color:var(--danger);">Invalid report URL. Please check the link and try again.</p>
        </div>
      `;
      return;
    }

    container.className = "view-report";
    setPageMetadata({
      title: "Monthly Revenue Report",
      description: "City-specific monthly tax revenue report from MuniRev.",
      path: `/report/${encodeURIComponent(copo)}/${year}/${month}`,
    });

    showLoading(container);

    getMonthlyReport(copo, year, month)
      .then((data) => {
        setPageMetadata({
          title: `${data.city_name} — ${data.period_label} Revenue Report`,
          description: `Sales, use, and lodging tax revenue report for ${data.city_name} — ${data.period_label}.`,
          path: `/report/${encodeURIComponent(copo)}/${year}/${month}`,
        });
        renderReport(container, data);
      })
      .catch((error: unknown) => {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to load the monthly report. Please try again.";
        container.innerHTML = `
          <div style="padding:40px;text-align:center;">
            <p class="body-copy" style="color:var(--danger);">${escapeHtml(message)}</p>
            <a href="/" class="button button-ghost" style="margin-top:16px;">Return home</a>
          </div>
        `;
      });
  },

  destroy(): void {
    // Highcharts charts self-manage their containers; no cleanup needed.
  },
};
