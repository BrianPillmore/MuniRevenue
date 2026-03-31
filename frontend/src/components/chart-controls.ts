/* ══════════════════════════════════════════════
   Chart analysis controls -- reusable pill bar
   ══════════════════════════════════════════════ */

export type SmoothingType = "none" | "3mo" | "6mo" | "ttm";
export type DisplayMode = "amount" | "pct_change";

export interface ChartControlsOptions {
  onSmoothingChange: (type: SmoothingType) => void;
  onSeasonalToggle: (adjusted: boolean) => void;
  onTrendlineToggle: (show: boolean) => void;
  onYAxisZeroToggle: (fromZero: boolean) => void;
  onDisplayModeChange?: (mode: DisplayMode) => void;
  showSeasonalToggle?: boolean; // default true
  showTrendline?: boolean; // default true
  showDisplayMode?: boolean; // default true
}

interface ControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
  displayMode: DisplayMode;
}

export function renderChartControls(
  container: HTMLElement,
  options: ChartControlsOptions,
): void {
  const showSeasonal = options.showSeasonalToggle !== false;
  const showTrendline = options.showTrendline !== false;
  const showDisplayMode = options.showDisplayMode !== false;

  /* State lives here — single source of truth for button active states */
  const state: ControlState = {
    smoothing: "none",
    seasonal: false,
    trendline: false,
    yAxisZero: false,
    displayMode: "amount",
  };

  /* Tooltip descriptions for each control */
  const tooltips: Record<string, string> = {
    "smoothing:none": "Show raw monthly data without smoothing",
    "smoothing:3mo": "3-month rolling average smooths short-term noise",
    "smoothing:6mo": "6-month rolling average shows medium-term trends",
    "smoothing:ttm": "Trailing 12-month average (annualized trend)",
    "seasonal:nominal": "Show actual reported values",
    "seasonal:adjusted": "Remove predictable seasonal patterns to reveal underlying trend",
    "trendline:toggle": "Overlay a linear trendline showing overall direction",
    "displaymode:amount": "Show dollar amounts on Y-axis",
    "displaymode:pct_change": "Show month-over-month percent change",
    "yaxis:toggle": "Set Y-axis minimum to zero for context",
  };

  function render(): void {
    function btn(group: string, value: string, label: string, isActive: boolean): string {
      const tip = tooltips[`${group}:${value}`] || "";
      return `<button class="chart-ctrl-btn${isActive ? " is-active" : ""}" data-group="${group}" data-value="${value}" title="${tip}">${label}</button>`;
    }

    const smoothingButtons = ([
      ["none", "Raw"],
      ["3mo", "3-Mo"],
      ["6mo", "6-Mo"],
      ["ttm", "TTM"],
    ] as [SmoothingType, string][])
      .map(([value, label]) => btn("smoothing", value, label, state.smoothing === value))
      .join("");

    const seasonalGroup = showSeasonal
      ? `
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Adjustment</span>
          <div class="chart-ctrl-pills">
            ${btn("seasonal", "nominal", "Nominal", !state.seasonal)}
            ${btn("seasonal", "adjusted", "Seasonally Adj", state.seasonal)}
          </div>
        </div>
      `
      : "";

    const trendlineGroup = showTrendline
      ? `
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Overlay</span>
          <div class="chart-ctrl-pills">
            ${btn("trendline", "toggle", "Trendline", state.trendline)}
          </div>
        </div>
      `
      : "";

    const displayModeGroup = showDisplayMode
      ? `
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Display</span>
          <div class="chart-ctrl-pills">
            ${btn("displaymode", "amount", "$ Amount", state.displayMode === "amount")}
            ${btn("displaymode", "pct_change", "% Change", state.displayMode === "pct_change")}
          </div>
        </div>
      `
      : "";

    container.innerHTML = `
      <div class="chart-controls">
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Smoothing</span>
          <div class="chart-ctrl-pills">${smoothingButtons}</div>
        </div>
        ${seasonalGroup}
        ${trendlineGroup}
        ${displayModeGroup}
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Y-Axis</span>
          <div class="chart-ctrl-pills">
            <button class="chart-ctrl-btn chart-ctrl-toggle${state.yAxisZero ? " is-active" : ""}" data-group="yaxis" data-value="toggle">From Zero</button>
          </div>
        </div>
      </div>
    `;

    /* Attach click handlers */
    container.querySelectorAll<HTMLButtonElement>(".chart-ctrl-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const group = btn.dataset.group;
        const value = btn.dataset.value;

        switch (group) {
          case "smoothing":
            state.smoothing = value as SmoothingType;
            options.onSmoothingChange(state.smoothing);
            break;
          case "seasonal":
            state.seasonal = value === "adjusted";
            options.onSeasonalToggle(state.seasonal);
            break;
          case "trendline":
            state.trendline = !state.trendline;
            options.onTrendlineToggle(state.trendline);
            break;
          case "displaymode":
            state.displayMode = value as DisplayMode;
            if (options.onDisplayModeChange) {
              options.onDisplayModeChange(state.displayMode);
            }
            break;
          case "yaxis":
            state.yAxisZero = !state.yAxisZero;
            options.onYAxisZeroToggle(state.yAxisZero);
            break;
        }

        render();
      });
    });
  }

  render();
}
