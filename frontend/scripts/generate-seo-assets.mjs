import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const siteUrl = process.env.VITE_SITE_URL ?? "https://munirevenue.com";
const sourcePublicDir = path.resolve(__dirname, "../public");
const publicDir = path.resolve(__dirname, "../.generated-public");
const dataDir = path.resolve(__dirname, "../../data/parsed");
const today = new Date().toISOString().slice(0, 10);
const featuredCityLimit = 100;

const appRoutes = [
  "/",
  "/city",
  "/county",
  "/compare",
  "/forecast",
  "/anomalies",
  "/missed-filings",
  "/rankings",
  "/trends",
  "/about",
];

const PAGE_STYLES = `
  :root {
    color-scheme: light;
    --bg: #f4f1ea;
    --surface: #fffdf8;
    --ink: #1f2933;
    --muted: #5c6578;
    --brand: #15324a;
    --accent: #b8832f;
    --line: rgba(21, 50, 74, 0.14);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background:
      radial-gradient(circle at top right, rgba(184,131,47,0.12), transparent 28%),
      linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
    color: var(--ink);
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.6;
  }
  a { color: var(--brand); }
  main {
    max-width: 1080px;
    margin: 0 auto;
    padding: 40px 24px 80px;
  }
  .eyebrow {
    margin: 0 0 10px;
    font: 700 0.78rem/1.2 "Segoe UI", sans-serif;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
  }
  .hero,
  .panel {
    background: rgba(255, 253, 248, 0.92);
    border: 1px solid var(--line);
    border-radius: 22px;
    box-shadow: 0 18px 50px rgba(21, 50, 74, 0.08);
  }
  .hero {
    padding: 42px 36px;
    margin-bottom: 24px;
  }
  h1, h2, h3 {
    margin: 0 0 12px;
    color: var(--brand);
    line-height: 1.15;
  }
  h1 { font-size: clamp(2rem, 4vw, 3.3rem); }
  h2 { font-size: clamp(1.4rem, 3vw, 2rem); }
  p { margin: 0 0 12px; }
  .lede { font-size: 1.05rem; max-width: 760px; color: #334155; }
  .grid {
    display: grid;
    gap: 18px;
  }
  .grid-2 { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
  .grid-3 { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
  .panel { padding: 26px 24px; }
  .metric {
    font: 700 1.55rem/1.1 "Segoe UI", sans-serif;
    color: var(--brand);
  }
  .metric-label {
    margin-bottom: 6px;
    font: 600 0.82rem/1.2 "Segoe UI", sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }
  .button-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 18px;
  }
  .button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 16px;
    border-radius: 999px;
    border: 1px solid var(--brand);
    font: 600 0.92rem/1 "Segoe UI", sans-serif;
    text-decoration: none;
  }
  .button-primary {
    background: var(--brand);
    color: #fffdf8;
  }
  .button-secondary {
    background: transparent;
    color: var(--brand);
  }
  .breadcrumbs {
    margin: 0 0 18px;
    font: 600 0.82rem/1.4 "Segoe UI", sans-serif;
    color: var(--muted);
  }
  .breadcrumbs a {
    color: var(--muted);
    text-decoration: none;
  }
  .list {
    margin: 0;
    padding-left: 18px;
  }
  .directory-list {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    padding: 0;
    margin: 0;
    list-style: none;
  }
  .directory-list li {
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255,255,255,0.72);
  }
  .directory-list strong {
    display: block;
    color: var(--brand);
    margin-bottom: 4px;
  }
  .muted { color: var(--muted); }
  .section-stack {
    display: grid;
    gap: 24px;
    margin-top: 24px;
  }
  .footer-note {
    margin-top: 28px;
    font-size: 0.9rem;
    color: var(--muted);
  }
`;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function slugify(value) {
  return String(value ?? "")
    .toLowerCase()
    .replaceAll("&", " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function absoluteUrl(routePath) {
  return new URL(routePath, siteUrl).toString();
}

function parseCsv(text) {
  const rows = [];
  let currentField = "";
  let currentRow = [];
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === '"') {
      if (inQuotes && next === '"') {
        currentField += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      currentRow.push(currentField);
      currentField = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") index += 1;
      if (currentField !== "" || currentRow.length > 0) {
        currentRow.push(currentField);
        rows.push(currentRow);
        currentRow = [];
        currentField = "";
      }
      continue;
    }

    currentField += char;
  }

  if (currentField !== "" || currentRow.length > 0) {
    currentRow.push(currentField);
    rows.push(currentRow);
  }

  const [header = [], ...dataRows] = rows;
  return dataRows.map((row) =>
    Object.fromEntries(header.map((key, columnIndex) => [key, row[columnIndex] ?? ""])),
  );
}

function parseSummaryValue(raw) {
  if (!raw) return null;
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseTaxTypes(raw) {
  if (!raw) return [];
  return raw
    .split(",")
    .map((item) => item.replaceAll('"', "").trim())
    .filter(Boolean);
}

function buildUniqueSlugs(items, keyBuilder) {
  const used = new Set();
  return items.map((item) => {
    const primary = slugify(keyBuilder(item)) || item.copo.toLowerCase();
    let candidate = primary;
    let suffix = 2;

    while (used.has(candidate)) {
      candidate = `${primary}-${suffix}`;
      suffix += 1;
    }

    used.add(candidate);
    return { ...item, slug: candidate };
  });
}

function parseData() {
  return Promise.all([
    fs.readFile(path.join(dataDir, "copo_directory.csv"), "utf8"),
    fs.readFile(path.join(dataDir, "jurisdiction_summary.csv"), "utf8"),
  ]).then(([directoryCsv, summaryCsv]) => {
    const jurisdictions = parseCsv(directoryCsv);
    const summaries = parseCsv(summaryCsv);
    const summaryByCopo = new Map(
      summaries.map((row) => [
        row.copo,
        {
          recordCount: Number.parseInt(row.record_count || "0", 10) || 0,
          taxTypes: parseTaxTypes(row.tax_types),
          dateRange: row.date_range || "",
          totalReturned: parseSummaryValue(row.total_returned),
        },
      ]),
    );

    const enriched = jurisdictions.map((row) => {
      const summary = summaryByCopo.get(row.copo) ?? {
        recordCount: 0,
        taxTypes: [],
        dateRange: "",
        totalReturned: null,
      };

      return {
        copo: row.copo,
        name: row.name,
        jurisdictionType: row.jurisdiction_type,
        countyName: row.county || null,
        ...summary,
      };
    });

    const counties = buildUniqueSlugs(
      enriched
        .filter((item) => item.jurisdictionType === "county")
        .sort((left, right) => (right.totalReturned ?? -1) - (left.totalReturned ?? -1) || left.name.localeCompare(right.name)),
      (item) => item.name,
    );

    const cities = buildUniqueSlugs(
      enriched
        .filter((item) => item.jurisdictionType === "city")
        .sort((left, right) => (right.totalReturned ?? -1) - (left.totalReturned ?? -1) || left.name.localeCompare(right.name)),
      (item) => `${item.name}-${item.countyName ?? item.copo}`,
    );

    return { cities, counties };
  });
}

function organizationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "MuniRevenue",
    url: siteUrl,
    description:
      "Municipal revenue intelligence for Oklahoma cities and counties, including tax trends, anomalies, forecasts, and missed filing signals.",
  };
}

function websiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "MuniRevenue",
    url: siteUrl,
  };
}

function datasetSchema({ name, description, path, keywords = [], spatialCoverage }) {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name,
    description,
    url: absoluteUrl(path),
    creator: {
      "@type": "Organization",
      name: "MuniRevenue",
      url: siteUrl,
    },
    keywords,
    spatialCoverage: spatialCoverage
      ? {
          "@type": "Place",
          name: spatialCoverage,
        }
      : undefined,
  };
}

function breadcrumbSchema(items) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}

function renderStructuredData(schemas) {
  return schemas
    .map(
      (schema) =>
        `<script type="application/ld+json">${JSON.stringify(schema)}</script>`,
    )
    .join("\n");
}

function pageShell({ title, description, canonicalPath, body, structuredData = [] }) {
  const fullTitle = `${title} | MuniRevenue`;
  const canonicalUrl = absoluteUrl(canonicalPath);

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(fullTitle)}</title>
    <meta name="description" content="${escapeHtml(description)}" />
    <meta property="og:title" content="${escapeHtml(fullTitle)}" />
    <meta property="og:description" content="${escapeHtml(description)}" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="${escapeHtml(canonicalUrl)}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtml(fullTitle)}" />
    <meta name="twitter:description" content="${escapeHtml(description)}" />
    <link rel="canonical" href="${escapeHtml(canonicalUrl)}" />
    <style>${PAGE_STYLES}</style>
    ${renderStructuredData(structuredData)}
  </head>
  <body>
    ${body}
  </body>
</html>
`;
}

function renderMetrics(metrics) {
  return `
    <div class="grid grid-3">
      ${metrics
        .map(
          (metric) => `
            <section class="panel">
              <div class="metric-label">${escapeHtml(metric.label)}</div>
              <div class="metric">${escapeHtml(metric.value)}</div>
              ${metric.note ? `<p class="muted">${escapeHtml(metric.note)}</p>` : ""}
            </section>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderCityDirectory(cities, featuredCities) {
  const featuredItems = featuredCities
    .map(
      (city) => `
        <li>
          <strong><a href="/oklahoma-cities/${city.slug}">${escapeHtml(city.name)}</a></strong>
          <span class="muted">${escapeHtml(city.countyName ?? "Oklahoma")} County · ${escapeHtml(formatCurrency(city.totalReturned))}</span>
        </li>
      `,
    )
    .join("");

  return pageShell({
    title: "Oklahoma Cities Revenue Directory",
    description:
      "Browse Oklahoma city revenue pages, featured municipal tax summaries, and links into MuniRevenue's city-level analysis tools.",
    canonicalPath: "/oklahoma-cities",
    structuredData: [
      organizationSchema(),
      websiteSchema(),
      breadcrumbSchema([
        { name: "Home", path: "/" },
        { name: "Oklahoma Cities", path: "/oklahoma-cities" },
      ]),
    ],
    body: `
      <main>
        <section class="hero">
          <p class="eyebrow">Directory</p>
          <h1>Oklahoma Cities Revenue Directory</h1>
          <p class="lede">
            Browse municipal revenue pages for Oklahoma cities, then jump into the live explorer for deeper tax trends,
            industry mix, anomalies, forecasts, and missed filing signals.
          </p>
          <div class="button-row">
            <a class="button button-primary" href="/city">Open Revenue Explorer</a>
            <a class="button button-secondary" href="/oklahoma-counties">Browse Counties</a>
          </div>
        </section>

        <div class="section-stack">
          ${renderMetrics([
            { label: "Cities with coverage", value: String(cities.length) },
            { label: "Featured landing pages", value: String(featuredCities.length) },
            { label: "Source", value: "Oklahoma Tax Commission" },
          ])}

          <section class="panel">
            <p class="eyebrow">Featured</p>
            <h2>First-wave city landing pages</h2>
            <ul class="directory-list">${featuredItems}</ul>
          </section>

          <section class="panel">
            <p class="eyebrow">Browse</p>
            <h2>All municipalities in the platform</h2>
            <p class="muted">These pages are generated from the current parsed jurisdiction catalog and link into the live city explorer for deeper investigation.</p>
            <ul class="directory-list">${cities
              .map(
                (city) => `
                  <li>
                    <strong><a href="/oklahoma-cities/${city.slug}">${escapeHtml(city.name)}</a></strong>
                    <span class="muted">${escapeHtml(city.countyName ?? "Unknown county")} County · ${escapeHtml(formatCurrency(city.totalReturned))}</span>
                  </li>
                `,
              )
              .join("")}</ul>
          </section>
        </div>
      </main>
    `,
  });
}

function renderCountyDirectory(counties) {
  const countyItems = counties
    .map(
      (county) => `
        <li>
          <strong><a href="/oklahoma-counties/${county.slug}">${escapeHtml(county.name)}</a></strong>
          <span class="muted">${escapeHtml(formatCurrency(county.totalReturned))}</span>
        </li>
      `,
    )
    .join("");

  return pageShell({
    title: "Oklahoma Counties Revenue Directory",
    description:
      "Browse Oklahoma county revenue pages and connect county rollups to the live MuniRevenue county and city analysis views.",
    canonicalPath: "/oklahoma-counties",
    structuredData: [
      organizationSchema(),
      websiteSchema(),
      breadcrumbSchema([
        { name: "Home", path: "/" },
        { name: "Oklahoma Counties", path: "/oklahoma-counties" },
      ]),
    ],
    body: `
      <main>
        <section class="hero">
          <p class="eyebrow">Directory</p>
          <h1>Oklahoma Counties Revenue Directory</h1>
          <p class="lede">
            Explore county-level revenue summaries for every Oklahoma county, then drill into the live county view to see
            city rollups, monthly totals, and related municipal pages.
          </p>
          <div class="button-row">
            <a class="button button-primary" href="/county">Open County View</a>
            <a class="button button-secondary" href="/oklahoma-cities">Browse Cities</a>
          </div>
        </section>

        <div class="section-stack">
          ${renderMetrics([
            { label: "Counties", value: String(counties.length) },
            { label: "Coverage", value: "Statewide" },
            { label: "Source", value: "Oklahoma Tax Commission" },
          ])}

          <section class="panel">
            <p class="eyebrow">Browse</p>
            <h2>County landing pages</h2>
            <ul class="directory-list">${countyItems}</ul>
          </section>
        </div>
      </main>
    `,
  });
}

function renderCityPage(city) {
  const description =
    `${city.name}, Oklahoma municipal revenue data${city.countyName ? ` for ${city.countyName} County` : ""}, including tax coverage, records, and links to live analysis tools.`;

  return pageShell({
    title: `${city.name}, Oklahoma Revenue Data`,
    description,
    canonicalPath: `/oklahoma-cities/${city.slug}`,
    structuredData: [
      organizationSchema(),
      breadcrumbSchema([
        { name: "Home", path: "/" },
        { name: "Oklahoma Cities", path: "/oklahoma-cities" },
        { name: city.name, path: `/oklahoma-cities/${city.slug}` },
      ]),
      datasetSchema({
        name: `${city.name} municipal revenue dataset summary`,
        description,
        path: `/oklahoma-cities/${city.slug}`,
        keywords: ["Oklahoma city revenue", "municipal tax data", city.name],
        spatialCoverage: city.name,
      }),
    ],
    body: `
      <main>
        <p class="breadcrumbs"><a href="/">Home</a> / <a href="/oklahoma-cities">Oklahoma Cities</a> / ${escapeHtml(city.name)}</p>

        <section class="hero">
          <p class="eyebrow">City Revenue Page</p>
          <h1>${escapeHtml(city.name)}, Oklahoma Revenue Data</h1>
          <p class="lede">
            ${escapeHtml(city.name)}${city.countyName ? ` is located in ${city.countyName} County, Oklahoma.` : " is an Oklahoma municipality."}
            This landing page summarizes the tax-revenue coverage currently available in MuniRevenue and points city officials to the right live analysis tools.
          </p>
          <div class="button-row">
            <a class="button button-primary" href="/city/${encodeURIComponent(city.copo)}">Open Revenue Explorer</a>
            <a class="button button-secondary" href="/forecast/${encodeURIComponent(city.copo)}">Open Forecasts</a>
          </div>
        </section>

        <div class="section-stack">
          ${renderMetrics([
            { label: "Total returned", value: formatCurrency(city.totalReturned) },
            { label: "Tax types", value: city.taxTypes.length ? city.taxTypes.join(", ") : "Not listed" },
            { label: "Records", value: String(city.recordCount || 0) },
            { label: "Date range", value: city.dateRange || "Not listed" },
          ])}

          <section class="panel">
            <p class="eyebrow">What to do next</p>
            <h2>Use the live app for deeper investigation</h2>
            <ul class="list">
              <li>Open the city explorer to review monthly sales, use, and lodging tax history.</li>
              <li>Check anomalies for unusual changes and supporting industry decomposition.</li>
              <li>Use missed filings signals to identify six-digit NAICS categories that may warrant follow-up.</li>
              <li>Use the forecast view for revenue planning and budget conversations.</li>
            </ul>
          </section>

          <section class="panel">
            <p class="eyebrow">Related pages</p>
            <h2>Related county and statewide pages</h2>
            <div class="button-row">
              ${city.countyName ? `<a class="button button-secondary" href="/county/${encodeURIComponent(city.countyName)}">Open ${escapeHtml(city.countyName)} County View</a>` : ""}
              <a class="button button-secondary" href="/anomalies">Statewide Anomalies</a>
              <a class="button button-secondary" href="/missed-filings">Missed Filings</a>
            </div>
            <p class="footer-note">MuniRevenue uses public Oklahoma Tax Commission data to help city clerks, finance directors, administrators, and elected officials spot revenue changes faster.</p>
          </section>
        </div>
      </main>
    `,
  });
}

function renderCountyPage(county) {
  const description =
    `${county.name}, Oklahoma revenue summary with county-level tax coverage and links into live municipal and county analysis tools.`;

  return pageShell({
    title: `${county.name}, Oklahoma Revenue Data`,
    description,
    canonicalPath: `/oklahoma-counties/${county.slug}`,
    structuredData: [
      organizationSchema(),
      breadcrumbSchema([
        { name: "Home", path: "/" },
        { name: "Oklahoma Counties", path: "/oklahoma-counties" },
        { name: county.name, path: `/oklahoma-counties/${county.slug}` },
      ]),
      datasetSchema({
        name: `${county.name} revenue dataset summary`,
        description,
        path: `/oklahoma-counties/${county.slug}`,
        keywords: ["Oklahoma county revenue", "county tax data", county.name],
        spatialCoverage: county.name,
      }),
    ],
    body: `
      <main>
        <p class="breadcrumbs"><a href="/">Home</a> / <a href="/oklahoma-counties">Oklahoma Counties</a> / ${escapeHtml(county.name)}</p>

        <section class="hero">
          <p class="eyebrow">County Revenue Page</p>
          <h1>${escapeHtml(county.name)}, Oklahoma Revenue Data</h1>
          <p class="lede">
            ${escapeHtml(county.name)} is covered in MuniRevenue with county-level revenue rollups and direct links to the cities that report inside the county.
          </p>
          <div class="button-row">
            <a class="button button-primary" href="/county/${encodeURIComponent(county.name.replace(/ County$/i, ""))}">Open County View</a>
            <a class="button button-secondary" href="/oklahoma-cities">Browse Cities</a>
          </div>
        </section>

        <div class="section-stack">
          ${renderMetrics([
            { label: "Total returned", value: formatCurrency(county.totalReturned) },
            { label: "Tax types", value: county.taxTypes.length ? county.taxTypes.join(", ") : "Not listed" },
            { label: "Records", value: String(county.recordCount || 0) },
            { label: "Date range", value: county.dateRange || "Not listed" },
          ])}

          <section class="panel">
            <p class="eyebrow">How counties use this</p>
            <h2>Use the county rollup to orient follow-up</h2>
            <ul class="list">
              <li>Review county-level monthly totals to spot broad tax shifts.</li>
              <li>Jump into city pages to understand which municipalities are driving movement.</li>
              <li>Use statewide anomaly and missed-filings pages to identify risk pockets worth reviewing.</li>
            </ul>
          </section>
        </div>
      </main>
    `,
  });
}

function renderInsightPage({
  title,
  description,
  canonicalPath,
  eyebrow,
  headline,
  lede,
  bullets,
  ctaHref,
  ctaLabel,
}) {
  return pageShell({
    title,
    description,
    canonicalPath,
    structuredData: [
      organizationSchema(),
      breadcrumbSchema([
        { name: "Home", path: "/" },
        { name: headline, path: canonicalPath },
      ]),
      datasetSchema({
        name: headline,
        description,
        path: canonicalPath,
        keywords: ["municipal revenue intelligence", "Oklahoma tax anomalies", "missed filings"],
      }),
    ],
    body: `
      <main>
        <p class="breadcrumbs"><a href="/">Home</a> / <span>Insights</span> / ${escapeHtml(headline)}</p>
        <section class="hero">
          <p class="eyebrow">${escapeHtml(eyebrow)}</p>
          <h1>${escapeHtml(headline)}</h1>
          <p class="lede">${escapeHtml(lede)}</p>
          <div class="button-row">
            <a class="button button-primary" href="${escapeHtml(ctaHref)}">${escapeHtml(ctaLabel)}</a>
            <a class="button button-secondary" href="/oklahoma-cities">Browse Oklahoma Cities</a>
          </div>
        </section>
        <div class="section-stack">
          <section class="panel">
            <p class="eyebrow">How it helps</p>
            <h2>What municipal teams can do with this signal</h2>
            <ul class="list">
              ${bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}
            </ul>
          </section>
        </div>
      </main>
    `,
  });
}

function buildRobotsTxt() {
  return `User-agent: *
Allow: /

Sitemap: ${absoluteUrl("/sitemap.xml")}
`;
}

function buildSitemapXml(paths) {
  const uniquePaths = Array.from(new Set(paths));
  const urlEntries = uniquePaths
    .map(
      (routePath) => `  <url>
    <loc>${absoluteUrl(routePath)}</loc>
    <lastmod>${today}</lastmod>
  </url>`,
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries}
</urlset>
`;
}

async function writePage(routePath, html) {
  const outputDir = routePath === "/"
    ? publicDir
    : path.join(publicDir, ...routePath.replace(/^\//, "").split("/"));

  await fs.mkdir(outputDir, { recursive: true });
  const outputFile = routePath === "/"
    ? path.join(outputDir, "index.seo-fallback.html")
    : path.join(outputDir, "index.html");
  await fs.writeFile(outputFile, html, "utf8");
}

async function copyDirectory(sourceDir, targetDir) {
  await fs.mkdir(targetDir, { recursive: true });
  const entries = await fs.readdir(sourceDir, { withFileTypes: true });

  await Promise.all(entries.map(async (entry) => {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);

    if (entry.isDirectory()) {
      await copyDirectory(sourcePath, targetPath);
      return;
    }

    await fs.copyFile(sourcePath, targetPath);
  }));
}

async function main() {
  const { cities, counties } = await parseData();
  const featuredCities = cities.filter((city) => city.totalReturned !== null).slice(0, featuredCityLimit);

  await fs.rm(publicDir, { recursive: true, force: true });
  await fs.mkdir(publicDir, { recursive: true });
  await copyDirectory(path.join(sourcePublicDir, "assets"), path.join(publicDir, "assets"));
  await Promise.all([
    fs.mkdir(path.join(publicDir, "oklahoma-cities"), { recursive: true }),
    fs.mkdir(path.join(publicDir, "oklahoma-counties"), { recursive: true }),
    fs.mkdir(path.join(publicDir, "insights"), { recursive: true }),
  ]);

  const generatedPaths = [
    "/oklahoma-cities",
    "/oklahoma-counties",
    "/insights/anomalies",
    "/insights/missed-filings",
    ...counties.map((county) => `/oklahoma-counties/${county.slug}`),
    ...cities.map((city) => `/oklahoma-cities/${city.slug}`),
  ];

  await Promise.all([
    fs.writeFile(path.join(publicDir, "robots.txt"), buildRobotsTxt(), "utf8"),
    fs.writeFile(
      path.join(publicDir, "sitemap.xml"),
      buildSitemapXml([...appRoutes, ...generatedPaths]),
      "utf8",
    ),
    writePage("/oklahoma-cities", renderCityDirectory(cities, featuredCities)),
    writePage("/oklahoma-counties", renderCountyDirectory(counties)),
    writePage(
      "/insights/anomalies",
      renderInsightPage({
        title: "Oklahoma Revenue Anomalies",
        description:
          "Understand how MuniRevenue surfaces unusual municipal revenue movements across Oklahoma and how to investigate those changes.",
        canonicalPath: "/insights/anomalies",
        eyebrow: "Insight",
        headline: "Oklahoma Revenue Anomalies",
        lede:
          "MuniRevenue flags unusual month-over-month and year-over-year shifts so city and county leaders can investigate the industries and tax streams behind abnormal movement.",
        bullets: [
          "Review statewide abnormal movements before they become budget surprises.",
          "Use industry decomposition to understand what sectors drove the change.",
          "Move from statewide scan to city-level exploration without starting from scratch.",
        ],
        ctaHref: "/anomalies",
        ctaLabel: "Open the anomalies feed",
      }),
    ),
    writePage(
      "/insights/missed-filings",
      renderInsightPage({
        title: "Missed Filings Detection",
        description:
          "Learn how MuniRevenue identifies likely missed municipal tax filings with NAICS-level run-rate gaps across Oklahoma cities.",
        canonicalPath: "/insights/missed-filings",
        eyebrow: "Insight",
        headline: "Missed Filings Detection",
        lede:
          "The missed-filings workflow points municipal teams toward six-digit NAICS categories whose current month run rate is materially below recent expectations.",
        bullets: [
          "Spot likely filing gaps by comparing current NAICS activity against rolling baselines.",
          "Prioritize follow-up by severity, missing-dollar amount, and expected industry share.",
          "Direct city clerks and finance staff toward the tax categories most likely to explain the shortfall.",
        ],
        ctaHref: "/missed-filings",
        ctaLabel: "Open missed filings",
      }),
    ),
    ...counties.map((county) =>
      writePage(`/oklahoma-counties/${county.slug}`, renderCountyPage(county))),
    ...cities.map((city) =>
      writePage(`/oklahoma-cities/${city.slug}`, renderCityPage(city))),
  ]);
}

await main();
