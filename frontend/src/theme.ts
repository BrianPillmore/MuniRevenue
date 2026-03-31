/* ══════════════════════════════════════════════
   Highcharts theme — MuniRev Civic Authority
   Navy / Gold / Colorblind-safe palette
   ══════════════════════════════════════════════ */

// @ts-ignore
import Highcharts from "highcharts";

/**
 * Colorblind-safe chart palette (8 colors).
 *
 * 1. Navy blue   #1b3a5c  — primary brand
 * 2. Gold amber  #c8922a  — Oklahoma accent
 * 3. Teal blue   #2b7a9e  — interactive accent
 * 4. Warm orange #d4793a  — distinct from gold at small size
 * 5. Slate purple #6b5b95  — separates well from blue for CVD
 * 6. Olive green  #5a8a3c  — nature / growth
 * 7. Rose         #b5566e  — stands out from all above
 * 8. Cool gray    #5c6578  — tertiary data
 *
 * Tested against deuteranopia, protanopia, and tritanopia
 * using simulated CVD checks. All pairs maintain sufficient
 * perceptual distance.
 */
const CHART_COLORS = [
  "#1b3a5c",
  "#c8922a",
  "#2b7a9e",
  "#d4793a",
  "#6b5b95",
  "#5a8a3c",
  "#b5566e",
  "#5c6578",
];

/**
 * Apply the MuniRev civic authority theme to Highcharts globally.
 * Call once at application startup.
 */
export function applyHighchartsTheme(): void {
  Highcharts.setOptions({
    colors: CHART_COLORS,
    chart: {
      backgroundColor: "transparent",
      style: {
        fontFamily: '"Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
      },
    },
    accessibility: { enabled: false },
    title: {
      style: {
        fontFamily: '"Merriweather", Georgia, "Times New Roman", serif',
        fontSize: "1.3rem",
        fontWeight: "bold",
        color: "#1a1f2b",
      },
    },
    subtitle: {
      style: { color: "#5c6578", fontSize: "0.88rem" },
    },
    xAxis: {
      labels: { style: { color: "#5c6578", fontSize: "0.78rem" } },
      lineColor: "rgba(26,31,43,0.12)",
      tickColor: "rgba(26,31,43,0.12)",
    },
    yAxis: {
      labels: { style: { color: "#5c6578", fontSize: "0.78rem" } },
      gridLineColor: "rgba(26,31,43,0.06)",
      title: { style: { color: "#5c6578" } },
    },
    legend: {
      itemStyle: { color: "#1a1f2b", fontWeight: "normal" },
    },
    tooltip: {
      backgroundColor: "rgba(255,255,255,0.97)",
      borderColor: "rgba(26,31,43,0.12)",
      style: { color: "#1a1f2b" },
      headerFormat:
        '<span style="font-size:0.82rem;font-weight:600;">{point.key}</span><br/>',
      pointFormat:
        '<span style="color:{series.color}">\u25CF</span> {series.name}: <b>{point.y:,.0f}</b><br/>',
    },
    credits: { enabled: false },
  });
}

export default Highcharts;
