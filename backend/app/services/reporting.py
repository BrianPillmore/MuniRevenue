from __future__ import annotations

from html import escape

from app.schemas import AnalysisResponse, ForecastPoint


def render_report_html(analysis: AnalysisResponse) -> str:
    highlights = "".join(f"<li>{escape(item)}</li>" for item in analysis.highlights)
    monthly_rows = "".join(
        """
        <tr>
          <td>{date}</td>
          <td>{returned}</td>
          <td>{mom}</td>
          <td>{yoy}</td>
        </tr>
        """.format(
            date=escape(row.voucher_date),
            returned=format_currency(row.returned),
            mom=format_percent(row.mom_pct),
            yoy=format_percent(row.yoy_pct),
        )
        for row in analysis.monthly_changes
    )
    seasonal_rows = "".join(
        """
        <tr>
          <td>{month}</td>
          <td>{obs}</td>
          <td>{mean}</td>
          <td>{median}</td>
          <td>{min_}</td>
          <td>{max_}</td>
        </tr>
        """.format(
            month=escape(row.month),
            obs=row.observations,
            mean=format_currency(row.mean_returned),
            median=format_currency(row.median_returned),
            min_=format_currency(row.min_returned),
            max_=format_currency(row.max_returned),
        )
        for row in analysis.seasonality
    )
    forecast_rows = "".join(
        """
        <tr>
          <td>{date}</td>
          <td>{basis}</td>
          <td>{projection}</td>
          <td>{lower}</td>
          <td>{upper}</td>
        </tr>
        """.format(
            date=escape(point.date),
            basis=escape(point.basis_month),
            projection=format_currency(point.projected_returned),
            lower=format_currency(point.lower_bound),
            upper=format_currency(point.upper_bound),
        )
        for point in analysis.forecast
    )

    anova_note = f"<p class='muted'>{escape(analysis.anova.note)}</p>" if analysis.anova.note else ""

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>MuniRev Analysis Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        --ink: #112233;
        --muted: #5f6f7a;
        --paper: #fffdf8;
        --line: #d8d2c8;
        --accent: #a63d40;
        --accent-soft: #f5e8d8;
        --teal: #2f6f74;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Trebuchet MS", "Gill Sans", sans-serif;
        color: var(--ink);
        background: linear-gradient(180deg, #f8efe1, #fffdf8 30%);
      }}
      main {{
        width: min(1100px, 100%);
        margin: 0 auto;
        padding: 40px 24px 64px;
      }}
      .hero {{
        background: white;
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 28px;
        box-shadow: 0 18px 40px rgba(17, 34, 51, 0.08);
      }}
      h1, h2 {{ font-family: Georgia, "Times New Roman", serif; }}
      h1 {{ margin: 0 0 8px; font-size: 2.4rem; }}
      h2 {{ margin: 0 0 16px; font-size: 1.5rem; }}
      p {{ line-height: 1.6; }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
        margin: 24px 0 0;
      }}
      .card {{
        background: linear-gradient(180deg, white, #fff7ec);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
      }}
      .label {{
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.74rem;
      }}
      .value {{
        margin-top: 8px;
        font-size: 1.45rem;
        font-weight: 700;
      }}
      .section {{
        margin-top: 28px;
        background: white;
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 24px;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 16px;
      }}
      th, td {{
        padding: 10px 12px;
        border-bottom: 1px solid #ece7df;
        text-align: left;
        font-size: 0.95rem;
      }}
      th {{ background: var(--accent-soft); }}
      .muted {{ color: var(--muted); }}
      .chart {{
        margin-top: 20px;
        padding: 16px;
        border-radius: 18px;
        background: linear-gradient(180deg, #fbf4ec, #ffffff);
        border: 1px solid #e9ddcf;
      }}
      .footer-note {{
        margin-top: 24px;
        color: var(--muted);
        font-size: 0.92rem;
      }}
      @media print {{
        body {{ background: white; }}
        .hero, .section {{ box-shadow: none; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <p class="label">MuniRev Report</p>
        <h1>Municipal Revenue Analysis</h1>
        <p class="muted">Municipal revenue analysis report.</p>
        <div class="grid">
          <div class="card">
            <div class="label">Records</div>
            <div class="value">{analysis.summary.records}</div>
          </div>
          <div class="card">
            <div class="label">Coverage</div>
            <div class="value">{escape(analysis.summary.first_date)} to {escape(analysis.summary.last_date)}</div>
          </div>
          <div class="card">
            <div class="label">Average Returned</div>
            <div class="value">{format_currency(analysis.summary.average_returned)}</div>
          </div>
          <div class="card">
            <div class="label">Latest Returned</div>
            <div class="value">{format_currency(analysis.summary.latest_returned)}</div>
          </div>
        </div>
      </section>

      <section class="section">
        <h2>Highlights</h2>
        <ul>{highlights}</ul>
      </section>

      <section class="section">
        <h2>ANOVA Summary</h2>
        <p><strong>Interpretation:</strong> {escape(analysis.anova.interpretation)}</p>
        <p><strong>F-statistic:</strong> {format_plain(analysis.anova.f_statistic)}<br />
        <strong>P-value:</strong> {format_plain(analysis.anova.p_value)}</p>
        {anova_note}
      </section>

      <section class="section">
        <h2>Monthly Changes</h2>
        <table>
          <thead>
            <tr>
              <th>Voucher Date</th>
              <th>Returned</th>
              <th>MoM</th>
              <th>YoY</th>
            </tr>
          </thead>
          <tbody>{monthly_rows}</tbody>
        </table>
      </section>

      <section class="section">
        <h2>Seasonality By Month</h2>
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th>Observations</th>
              <th>Mean</th>
              <th>Median</th>
              <th>Min</th>
              <th>Max</th>
            </tr>
          </thead>
          <tbody>{seasonal_rows}</tbody>
        </table>
      </section>

      <section class="section">
        <h2>12-Month Forecast</h2>
        <div class="chart">{build_forecast_svg(analysis.forecast)}</div>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Basis Month</th>
              <th>Projection</th>
              <th>Lower Bound</th>
              <th>Upper Bound</th>
            </tr>
          </thead>
          <tbody>{forecast_rows}</tbody>
        </table>
        <p class="footer-note">
          Disclaimer: This tool is provided as an analytical aid. Municipal users should pair the output with local
          finance review before making budget decisions.
        </p>
      </section>
    </main>
  </body>
</html>"""


def build_forecast_svg(points: list[ForecastPoint]) -> str:
    if not points:
        return "<p class='muted'>Not enough data was available to render a forecast chart.</p>"

    width = 900
    height = 280
    padding = 24
    values = [point.projected_returned for point in points] + [point.lower_bound for point in points] + [point.upper_bound for point in points]
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1.0)

    def project_x(index: int) -> float:
        return padding + index * ((width - padding * 2) / max(len(points) - 1, 1))

    def project_y(value: float) -> float:
        ratio = (value - min_value) / span
        return height - padding - ratio * (height - padding * 2)

    line_points = " ".join(f"{project_x(idx):.1f},{project_y(point.projected_returned):.1f}" for idx, point in enumerate(points))
    upper_points = [f"{project_x(idx):.1f},{project_y(point.upper_bound):.1f}" for idx, point in enumerate(points)]
    lower_points = [f"{project_x(idx):.1f},{project_y(point.lower_bound):.1f}" for idx, point in reversed(list(enumerate(points)))]
    polygon_points = " ".join(upper_points + lower_points)

    labels = "".join(
        f"<text x='{project_x(idx):.1f}' y='{height - 4}' font-size='11' text-anchor='middle' fill='#5f6f7a'>{escape(point.date[5:7] + '/' + point.date[2:4])}</text>"
        for idx, point in enumerate(points)
    )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="100%" role="img" aria-label="Forecast chart">
      <rect x="0" y="0" width="{width}" height="{height}" fill="white" rx="18" />
      <polygon points="{polygon_points}" fill="rgba(166, 61, 64, 0.18)" />
      <polyline points="{line_points}" fill="none" stroke="#2f6f74" stroke-width="4" stroke-linecap="round" />
      {labels}
    </svg>
    """


def format_currency(value: float) -> str:
    return f"${value:,.2f}"


def format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def format_plain(value: float | None) -> str:
    return "N/A" if value is None else str(value)
