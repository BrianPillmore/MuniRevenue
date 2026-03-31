/* ==================================================
   Chart download bar -- PNG / CSV / SVG
   WITHOUT the Highcharts exporting module
   ================================================== */

/**
 * Render a row of download buttons (PNG, CSV, SVG) for a Highcharts chart.
 *
 * PNG:  getSVG -> base64 svg -> Image -> Canvas -> toDataURL -> download
 * CSV:  categories + series -> CSV string -> Blob -> download
 * SVG:  getSVG -> Blob -> download
 */
export function renderChartDownloadBar(
  container: HTMLElement,
  chart: any,
  categories: string[],
  seriesData: { name: string; data: (number | null)[] }[],
  filenameBase: string,
): void {
  container.innerHTML = `
    <div class="chart-download-bar">
      <button class="chart-dl-btn" data-fmt="png">PNG</button>
      <button class="chart-dl-btn" data-fmt="csv">CSV</button>
      <button class="chart-dl-btn" data-fmt="svg">SVG</button>
    </div>
  `;

  container.querySelectorAll<HTMLButtonElement>(".chart-dl-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fmt = btn.dataset.fmt;
      switch (fmt) {
        case "png":
          downloadPng(chart, filenameBase);
          break;
        case "csv":
          downloadCsv(categories, seriesData, filenameBase);
          break;
        case "svg":
          downloadSvg(chart, filenameBase);
          break;
      }
    });
  });
}

/* ---- PNG via canvas ---- */

function downloadPng(chart: any, filenameBase: string): void {
  const svgString = chart.getSVG();
  const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  const img = new Image();

  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = img.width * 2;
    canvas.height = img.height * 2;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(2, 2);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);

    canvas.toBlob((blob) => {
      if (!blob) return;
      triggerDownload(blob, `${filenameBase}.png`);
    }, "image/png");
  };

  img.src = url;
}

/* ---- CSV ---- */

function downloadCsv(
  categories: string[],
  seriesData: { name: string; data: (number | null)[] }[],
  filenameBase: string,
): void {
  const header = ["Date", ...seriesData.map((s) => s.name)].join(",");
  const rows = categories.map((cat, i) => {
    const vals = seriesData.map((s) => {
      const v = s.data[i];
      return v !== null && v !== undefined ? String(v) : "";
    });
    return [cat, ...vals].join(",");
  });
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  triggerDownload(blob, `${filenameBase}.csv`);
}

/* ---- SVG ---- */

function downloadSvg(chart: any, filenameBase: string): void {
  const svgString = chart.getSVG();
  const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  triggerDownload(blob, `${filenameBase}.svg`);
}

/* ---- Common download trigger ---- */

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
