/* ══════════════════════════════════════════════
   Highcharts theme and module initialization
   ══════════════════════════════════════════════ */

// @ts-ignore
import Highcharts from "highcharts";
// @ts-ignore
import HighchartsMore from "highcharts/highcharts-more";
// @ts-ignore
import Treemap from "highcharts/modules/treemap";
// @ts-ignore
import Heatmap from "highcharts/modules/heatmap";

/* Initialize optional modules */
// @ts-ignore
HighchartsMore(Highcharts);
// @ts-ignore
Treemap(Highcharts);
// @ts-ignore
Heatmap(Highcharts);

/**
 * Apply the MuniRev warm paper theme to Highcharts globally.
 * Call once at application startup.
 */
export function applyHighchartsTheme(): void {
  Highcharts.setOptions({
    colors: ["#1d6b70", "#a63d40", "#d4a843", "#2f6f74", "#c17f59", "#5d6b75", "#8c4e4f"],
    chart: {
      backgroundColor: "transparent",
      style: {
        fontFamily: '"Trebuchet MS", "Lucida Sans Unicode", sans-serif',
      },
    },
    title: {
      style: {
        fontFamily: 'Georgia, "Times New Roman", serif',
        fontSize: "1.3rem",
        fontWeight: "bold",
        color: "#102231",
      },
    },
    subtitle: {
      style: { color: "#5d6b75", fontSize: "0.88rem" },
    },
    xAxis: {
      labels: { style: { color: "#5d6b75", fontSize: "0.78rem" } },
      lineColor: "rgba(16,34,49,0.12)",
      tickColor: "rgba(16,34,49,0.12)",
    },
    yAxis: {
      labels: { style: { color: "#5d6b75", fontSize: "0.78rem" } },
      gridLineColor: "rgba(16,34,49,0.08)",
      title: { style: { color: "#5d6b75" } },
    },
    legend: {
      itemStyle: { color: "#102231", fontWeight: "normal" },
    },
    tooltip: {
      backgroundColor: "rgba(255,252,246,0.96)",
      borderColor: "rgba(16,34,49,0.12)",
      style: { color: "#102231" },
    },
    credits: { enabled: false },
  });
}

export default Highcharts;
