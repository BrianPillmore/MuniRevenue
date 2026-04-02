/* ══════════════════════════════════════════════
   MuniRev — Application entry point
   ══════════════════════════════════════════════ */

import "./styles.css";
import { refreshSession } from "./auth";
import { applyHighchartsTheme } from "./theme";
import { renderSidebar } from "./components/sidebar";
import { initRouter } from "./router";
import { ROUTES } from "./paths";
import { overviewView } from "./views/overview";
import { cityView } from "./views/city";
import { aboutView } from "./views/about";
import { accountView } from "./views/account";
import { rankingsView } from "./views/rankings";
import { trendsView } from "./views/trends";
import { forecastView } from "./views/forecast";
import { anomaliesView } from "./views/anomalies";
import { missedFilingsView } from "./views/missed-filings";
import { compareView } from "./views/compare";
import { countyView } from "./views/county";
import { exportView } from "./views/export";
import { loginView } from "./views/login";

/* ── Initialize Highcharts theme ── */
applyHighchartsTheme();
void refreshSession();

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
  [ROUTES.overview]: overviewView,
  [ROUTES.city]: cityView,
  [`${ROUTES.city}/:copo`]: cityView,
  [`${ROUTES.city}/:copo/:tab`]: cityView,
  [ROUTES.login]: loginView,
  [ROUTES.account]: accountView,
  [ROUTES.forecast]: forecastView,
  [`${ROUTES.forecast}/:copo`]: forecastView,
  [ROUTES.anomalies]: anomaliesView,
  [ROUTES.missedFilings]: missedFilingsView,
  [ROUTES.compare]: compareView,
  [ROUTES.county]: countyView,
  [`${ROUTES.county}/:county`]: countyView,
  [ROUTES.export]: exportView,
  [ROUTES.rankings]: rankingsView,
  [ROUTES.trends]: trendsView,
  [ROUTES.about]: aboutView,
});

/* ── Reveal app once rendered (prevents flash of unstyled content) ── */
requestAnimationFrame(() => app.classList.add("ready"));
