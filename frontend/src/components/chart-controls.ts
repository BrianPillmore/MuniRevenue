/* ══════════════════════════════════════════════
   Chart analysis controls -- reusable pill bar
   ══════════════════════════════════════════════ */

export type SmoothingType = "none" | "3mo" | "6mo" | "ttm";

export interface ChartControlsOptions {
  onSmoothingChange: (type: SmoothingType) => void;
  onSeasonalToggle: (adjusted: boolean) => void;
  onTrendlineToggle: (show: boolean) => void;
  onYAxisZeroToggle: (fromZero: boolean) => void;
  showSeasonalToggle?: boolean; // default true
  showTrendline?: boolean; // default true
}

interface ControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
}

export function renderChartControls(
  container: HTMLElement,
  options: ChartControlsOptions,
): void {
  const showSeasonal = options.showSeasonalToggle !== false;
  const showTrendline = options.showTrendline !== false;

  const state: ControlState = {
    smoothing: "none",
    seasonal: false,
    trendline: false,
    yAxisZero: false,
  };

  function render(): void {
    const smoothingButtons = ([
      ["none", "Raw"],
      ["3mo", "3-Mo"],
      ["6mo", "6-Mo"],
      ["ttm", "TTM"],
    ] as [SmoothingType, string][])
      .map(
        ([value, label]) =>
          `<button class="chart-ctrl-btn${state.smoothing === value ? " is-active" : ""}" data-group="smoothing" data-value="${value}">${label}</button>`,
      )
      .join("");

    const seasonalGroup = showSeasonal
      ? `
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Adjustment</span>
          <div class="chart-ctrl-pills">
            <button class="chart-ctrl-btn${!state.seasonal ? " is-active" : ""}" data-group="seasonal" data-value="nominal">Nominal</button>
            <button class="chart-ctrl-btn${state.seasonal ? " is-active" : ""}" data-group="seasonal" data-value="adjusted">Seasonally Adj</button>
          </div>
        </div>
      `
      : "";

    const trendlineGroup = showTrendline
      ? `
        <div class="chart-ctrl-group">
          <span class="chart-ctrl-label">Overlay</span>
          <div class="chart-ctrl-pills">
            <button class="chart-ctrl-btn chart-ctrl-toggle${state.trendline ? " is-active" : ""}" data-group="trendline" data-value="toggle">Trendline</button>
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
