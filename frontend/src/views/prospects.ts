/* ══════════════════════════════════════════════
   Prospects CRM — admin only
   All Oklahoma jurisdictions as potential prospects
   ══════════════════════════════════════════════ */

import { getProspectDetail, getProspects } from "../api";
import type {
    ProspectDetailResponse,
    ProspectRow,
    ProspectsListResponse,
    View,
} from "../types";

type TierFilter = "" | "tier1" | "tier2" | "tier3";
type TypeFilter = "" | "city" | "county";

let data: ProspectsListResponse | null = null;
let tierFilter: TierFilter = "";
let typeFilter: TypeFilter = "";
let searchQuery = "";
let searchDebounce: ReturnType<typeof setTimeout> | null = null;
let expandedJurisdiction: string | null = null;
let detailCache: Record<string, ProspectDetailResponse> = {};
let _container: HTMLElement | null = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tierLabel(tier: string): string {
  switch (tier) {
    case "tier1": return "Tier 1";
    case "tier2": return "Tier 2";
    case "tier3": return "Tier 3";
    default: return tier;
  }
}

function tierBadge(tier: string): string {
  const cls = tier === "tier1" ? "prospects-tier--1"
            : tier === "tier2" ? "prospects-tier--2"
            : "prospects-tier--3";
  return `<span class="prospects-tier-badge ${cls}">${tierLabel(tier)}</span>`;
}

function readyBadge(ready: boolean): string {
  return ready
    ? `<span class="gtm-badge gtm-badge--ok">Ready</span>`
    : `<span class="gtm-badge gtm-badge--none">No Email</span>`;
}

function fmtPop(pop: number | null): string {
  if (pop == null) return "—";
  return pop.toLocaleString();
}

function pct(n: number, d: number): string {
  if (!d) return "—";
  return `${Math.round((n / d) * 100)}%`;
}

// ---------------------------------------------------------------------------
// Stats cards
// ---------------------------------------------------------------------------

function renderStats(stats: ProspectsListResponse["stats"]): string {
  const cards = [
    {
      label: "Total Prospects",
      value: String(stats.total_prospects),
      sub: `${stats.tier1_count} Tier 1 · ${stats.tier2_count} Tier 2 · ${stats.tier3_count} Tier 3`,
    },
    {
      label: "Outreach Ready",
      value: String(stats.outreach_ready),
      sub: `${pct(stats.outreach_ready, stats.total_prospects)} of all prospects`,
    },
    {
      label: "Total Contacts",
      value: String(stats.total_contacts),
      sub: `${stats.total_contacts_with_email} with email`,
    },
    {
      label: "With Users",
      value: String(stats.with_user),
      sub: `${pct(stats.with_user, stats.total_prospects)} signed up`,
    },
  ];

  return `
    <div class="prospects-stats-grid">
      ${cards.map(c => `
        <div class="gtm-stat-card">
          <p class="gtm-stat-value">${c.value}</p>
          <p class="gtm-stat-label">${c.label}</p>
          <p class="gtm-stat-sub">${c.sub}</p>
        </div>
      `).join("")}
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Tier breakdown bar
// ---------------------------------------------------------------------------

function renderTierBreakdown(stats: ProspectsListResponse["stats"]): string {
  const total = stats.total_prospects || 1;
  const t1Pct = (stats.tier1_count / total) * 100;
  const t2Pct = (stats.tier2_count / total) * 100;
  const t3Pct = (stats.tier3_count / total) * 100;

  return `
    <div class="prospects-tier-bar-container">
      <div class="prospects-tier-bar">
        <div class="prospects-tier-bar__seg prospects-tier-bar__seg--1" style="width:${t1Pct}%"
          title="Tier 1: ${stats.tier1_count}"></div>
        <div class="prospects-tier-bar__seg prospects-tier-bar__seg--2" style="width:${t2Pct}%"
          title="Tier 2: ${stats.tier2_count}"></div>
        <div class="prospects-tier-bar__seg prospects-tier-bar__seg--3" style="width:${t3Pct}%"
          title="Tier 3: ${stats.tier3_count}"></div>
      </div>
      <div class="prospects-tier-legend">
        <span class="prospects-tier-legend__item">
          <span class="prospects-tier-dot prospects-tier-dot--1"></span>
          Tier 1 — Top 20 cities (${stats.tier1_count})
        </span>
        <span class="prospects-tier-legend__item">
          <span class="prospects-tier-dot prospects-tier-dot--2"></span>
          Tier 2 — Mid-size + counties (${stats.tier2_count})
        </span>
        <span class="prospects-tier-legend__item">
          <span class="prospects-tier-dot prospects-tier-dot--3"></span>
          Tier 3 — Small municipalities (${stats.tier3_count})
        </span>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Prospect detail (expanded row)
// ---------------------------------------------------------------------------

function renderDetail(detail: ProspectDetailResponse): string {
  if (!detail.contacts.length) {
    return `<div class="prospects-detail"><p class="gtm-empty">No contacts on file.</p></div>`;
  }

  const rows = detail.contacts.map(c => {
    const emailCell = c.email
      ? `<a href="mailto:${c.email}" class="gtm-email-link">${c.email}</a>`
      : "—";
    return `
      <tr>
        <td>${c.office_title ?? "—"}</td>
        <td>${c.district_or_ward ?? "—"}</td>
        <td class="prospects-detail__name">${c.person_name ?? "—"}</td>
        <td>${c.phone ?? "—"}</td>
        <td>${emailCell}</td>
        <td>${c.contact_type ?? "—"}</td>
        <td class="gtm-col-center">${c.verified_date ? c.verified_date.slice(0, 10) : "—"}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="prospects-detail">
      <p class="prospects-detail__count">${detail.contacts.length} contacts · ${detail.user_count} active users</p>
      <div class="gtm-table-wrapper">
        <table class="gtm-table prospects-detail__table">
          <thead>
            <tr>
              <th>Title / Office</th>
              <th>District</th>
              <th>Name</th>
              <th>Phone</th>
              <th>Email</th>
              <th>Type</th>
              <th class="gtm-col-center">Verified</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Prospects table
// ---------------------------------------------------------------------------

function renderTable(prospects: ProspectRow[]): string {
  if (!prospects.length) {
    return `<p class="gtm-empty">No prospects match your filters.</p>`;
  }

  const rows = prospects.map(p => {
    const isExpanded = expandedJurisdiction === p.jurisdiction_name;
    const typeBadge = p.jurisdiction_type === "city"
      ? `<span class="gtm-badge gtm-badge--ok">city</span>`
      : `<span class="gtm-badge gtm-badge--county">county</span>`;

    const detailHtml = isExpanded
      ? (detailCache[p.jurisdiction_name]
          ? renderDetail(detailCache[p.jurisdiction_name])
          : `<div class="prospects-detail"><div class="loading-spinner"></div></div>`)
      : "";

    return `
      <tr class="prospects-row${isExpanded ? " prospects-row--expanded" : ""}"
          data-jurisdiction="${p.jurisdiction_name}">
        <td class="prospects-col-expand">
          <button class="prospects-expand-btn" data-expand="${p.jurisdiction_name}"
            aria-label="Expand ${p.jurisdiction_name}">${isExpanded ? "▾" : "▸"}</button>
        </td>
        <td class="gtm-col-name">${p.jurisdiction_name}</td>
        <td class="gtm-col-center">${typeBadge}</td>
        <td>${p.county ?? "—"}</td>
        <td class="gtm-col-center">${tierBadge(p.tier)}</td>
        <td class="gtm-col-right">${fmtPop(p.population_2024)}</td>
        <td class="gtm-col-center">${p.total_contacts}</td>
        <td class="gtm-col-center">${p.contacts_with_email}</td>
        <td class="gtm-col-center">${p.contacts_with_phone}</td>
        <td class="prospects-key-contact">
          ${p.key_contact_name
            ? `<span class="prospects-kc-name">${p.key_contact_name}</span>
               <span class="prospects-kc-title">${p.key_contact_title ?? ""}</span>`
            : "—"}
        </td>
        <td class="gtm-col-center">${readyBadge(p.outreach_ready)}</td>
        <td class="gtm-col-center">${p.user_count > 0
          ? `<span class="gtm-badge gtm-badge--ok">${p.user_count}</span>`
          : `<span class="gtm-badge gtm-badge--none">0</span>`}</td>
      </tr>
      ${detailHtml ? `<tr class="prospects-detail-row"><td colspan="12">${detailHtml}</td></tr>` : ""}
    `;
  }).join("");

  return `
    <p class="gtm-row-count">${prospects.length} prospects</p>
    <div class="gtm-table-wrapper">
      <table class="gtm-table prospects-table">
        <thead>
          <tr>
            <th style="width:30px"></th>
            <th>Jurisdiction</th>
            <th class="gtm-col-center">Type</th>
            <th>County</th>
            <th class="gtm-col-center">Tier</th>
            <th class="gtm-col-right">Population</th>
            <th class="gtm-col-center">Contacts</th>
            <th class="gtm-col-center">Emails</th>
            <th class="gtm-col-center">Phones</th>
            <th>Key Contact</th>
            <th class="gtm-col-center">Outreach</th>
            <th class="gtm-col-center">Users</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Loading + rendering
// ---------------------------------------------------------------------------

async function loadData(container: HTMLElement): Promise<void> {
  const tableEl = container.querySelector<HTMLElement>(".prospects-table-container");
  if (tableEl) tableEl.innerHTML = `<div class="loading-spinner"></div>`;

  try {
    data = await getProspects({
      tier: tierFilter || undefined,
      jtype: typeFilter || undefined,
      search: searchQuery || undefined,
    });

    const statsEl = container.querySelector<HTMLElement>(".prospects-stats-placeholder");
    if (statsEl && data) {
      statsEl.innerHTML = renderStats(data.stats) + renderTierBreakdown(data.stats);
    }

    renderTableContent(container);
  } catch (err) {
    if (tableEl) {
      tableEl.innerHTML = `<p class="error-message">Failed to load prospects: ${err instanceof Error ? err.message : String(err)}</p>`;
    }
  }
}

function renderTableContent(container: HTMLElement): void {
  const tableEl = container.querySelector<HTMLElement>(".prospects-table-container");
  if (!tableEl || !data) return;
  tableEl.innerHTML = renderTable(data.prospects);
  wireExpandButtons(container);
}

function wireExpandButtons(container: HTMLElement): void {
  container.querySelectorAll<HTMLButtonElement>(".prospects-expand-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.expand!;
      if (expandedJurisdiction === name) {
        expandedJurisdiction = null;
        renderTableContent(container);
        return;
      }
      expandedJurisdiction = name;
      renderTableContent(container);

      if (!detailCache[name]) {
        try {
          detailCache[name] = await getProspectDetail(name);
          if (expandedJurisdiction === name) {
            renderTableContent(container);
          }
        } catch {
          /* ignore — loading spinner will stay */
        }
      }
    });
  });
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export const prospectsView: View = {
  render(container: HTMLElement): void {
    _container = container;
    data = null;
    expandedJurisdiction = null;
    detailCache = {};
    tierFilter = "";
    typeFilter = "";
    searchQuery = "";

    container.innerHTML = `
      <div class="view-header">
        <h1 class="view-title">Prospects</h1>
        <p class="view-subtitle">All Oklahoma jurisdictions — outreach readiness, contacts, and pipeline status.</p>
      </div>

      <div class="prospects-stats-placeholder">
        <div class="loading-spinner"></div>
      </div>

      <div class="prospects-controls">
        <div class="prospects-filters">
          <select class="form-select prospects-tier-filter" aria-label="Filter by tier">
            <option value="">All Tiers</option>
            <option value="tier1">Tier 1 — Top 20</option>
            <option value="tier2">Tier 2 — Mid-size + Counties</option>
            <option value="tier3">Tier 3 — Small Towns</option>
          </select>
          <select class="form-select prospects-type-filter" aria-label="Filter by type">
            <option value="">All Types</option>
            <option value="city">Cities</option>
            <option value="county">Counties</option>
          </select>
        </div>
        <input
          class="gtm-search prospects-search"
          type="search"
          placeholder="Search by name…"
          aria-label="Search prospects"
        />
      </div>

      <div class="prospects-table-container">
        <div class="loading-spinner"></div>
      </div>
    `;

    // Wire filter controls
    const tierSel = container.querySelector<HTMLSelectElement>(".prospects-tier-filter");
    const typeSel = container.querySelector<HTMLSelectElement>(".prospects-type-filter");
    const searchEl = container.querySelector<HTMLInputElement>(".prospects-search");

    tierSel?.addEventListener("change", () => {
      tierFilter = (tierSel.value || "") as TierFilter;
      void loadData(container);
    });

    typeSel?.addEventListener("change", () => {
      typeFilter = (typeSel.value || "") as TypeFilter;
      void loadData(container);
    });

    searchEl?.addEventListener("input", () => {
      if (searchDebounce) clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        searchQuery = searchEl.value.trim();
        void loadData(container);
      }, 300);
    });

    void loadData(container);
  },

  destroy(): void {
    if (searchDebounce) clearTimeout(searchDebounce);
    _container = null;
    data = null;
    detailCache = {};
  },
};
