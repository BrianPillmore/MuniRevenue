/* ══════════════════════════════════════════════
   MuniRev — Application entry point
   ══════════════════════════════════════════════ */

import "./styles.css";
import { applyHighchartsTheme } from "./theme";
import { renderSidebar } from "./components/sidebar";
import { initRouter } from "./router";
import { overviewView } from "./views/overview";
import { cityView } from "./views/city";
import { aboutView } from "./views/about";
import { rankingsView } from "./views/rankings";
import { trendsView } from "./views/trends";
import { forecastView } from "./views/forecast";
import { anomaliesView } from "./views/anomalies";
import { compareView } from "./views/compare";
import { countyView } from "./views/county";
import { exportView } from "./views/export";

/* ── Initialize Highcharts theme ── */
applyHighchartsTheme();

/* ── Build app shell ── */

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Unable to find app root.");
}

app.innerHTML = `
  <div class="app-layout">
    <div id="sidebar-mount"></div>
    <main id="view-container" class="view-container"></main>
  </div>
`;

/* ── Render sidebar ── */
const sidebarMount = app.querySelector<HTMLElement>("#sidebar-mount")!;
renderSidebar(sidebarMount);

/* ── Initialize router ── */
const viewContainer = app.querySelector<HTMLElement>("#view-container")!;

initRouter(viewContainer, {
  "#/overview": overviewView,
  "#/city": cityView,
  "#/city/:copo": cityView,
  "#/city/:copo/:tab": cityView,
  "#/forecast": forecastView,
  "#/forecast/:copo": forecastView,
  "#/anomalies": anomaliesView,
  "#/compare": compareView,
  "#/county": countyView,
  "#/county/:county": countyView,
  "#/export": exportView,
  "#/rankings": rankingsView,
  "#/trends": trendsView,
  "#/about": aboutView,
});

/* ── Navigate to default if no hash is set ── */
if (!window.location.hash) {
  window.location.hash = "#/overview";
}
