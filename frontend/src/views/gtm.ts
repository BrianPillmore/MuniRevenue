/* ══════════════════════════════════════════════
   Go-to-Market / Admin Dashboard — super-admin only
   ══════════════════════════════════════════════ */

import { getGtmPipeline, getGtmUsers, getGtmContacts, sendGtmReports } from "../api";
import { navigateTo } from "../router";
import { ROUTES } from "../paths";
import { refreshSession } from "../auth";
import type {
  GtmCityRow,
  GtmContactRow,
  GtmPipelineResponse,
  GtmUsersResponse,
  GtmContactsResponse,
  View,
} from "../types";
import { formatCompactCurrency } from "../utils";

type ActiveTab = "cities" | "counties" | "users" | "contacts";

let activeTab: ActiveTab = "cities";
let pipelineData: GtmPipelineResponse | null = null;
let usersData: GtmUsersResponse | null = null;
let contactsData: GtmContactsResponse | null = null;
let filterQuery = "";
let contactsSearchDebounce: ReturnType<typeof setTimeout> | null = null;
let _container: HTMLElement | null = null;

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function pct(numerator: number, denominator: number): string {
  if (!denominator) return "—";
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function coverageBadge(count: number): string {
  if (count === 0) return `<span class="gtm-badge gtm-badge--none">none</span>`;
  return `<span class="gtm-badge gtm-badge--ok">${count}</span>`;
}

// ---------------------------------------------------------------------------
// Stats + funnel cards
// ---------------------------------------------------------------------------

function renderStatsCards(stats: GtmPipelineResponse["stats"]): string {
  const totalJurisdictions = stats.total_cities + stats.total_counties;

  const topCards = [
    {
      label: "Jurisdictions",
      value: String(totalJurisdictions),
      sub: `${stats.total_cities} cities · ${stats.total_counties} counties`,
    },
    {
      label: "Contacts",
      value: String(stats.total_contacts),
      sub: `${stats.total_contacts_with_email} w/ email · ${stats.total_contacts_with_phone} w/ phone`,
    },
    {
      label: "Active Users",
      value: String(stats.total_active_users),
      sub: `${stats.total_magic_links_sent} magic links sent`,
    },
  ];

  const citySteps = [
    { label: "Cities", value: stats.total_cities, pctVal: "" },
    { label: "w/ Contact", value: stats.cities_with_contact, pctVal: pct(stats.cities_with_contact, stats.total_cities) },
    { label: "w/ Email", value: stats.cities_with_email, pctVal: pct(stats.cities_with_email, stats.total_cities) },
    { label: "w/ User", value: stats.cities_with_user, pctVal: pct(stats.cities_with_user, stats.total_cities) },
  ];

  const countySteps = [
    { label: "Counties", value: stats.total_counties, pctVal: "" },
    { label: "w/ Contact", value: stats.counties_with_contact, pctVal: pct(stats.counties_with_contact, stats.total_counties) },
    { label: "w/ Email", value: stats.counties_with_email, pctVal: pct(stats.counties_with_email, stats.total_counties) },
    { label: "w/ User", value: stats.counties_with_user, pctVal: pct(stats.counties_with_user, stats.total_counties) },
  ];

  const renderFunnelStep = (step: { label: string; value: number; pctVal: string }, isFirst: boolean) => `
    <div class="gtm-funnel-step${isFirst ? " gtm-funnel-step--first" : ""}">
      ${!isFirst ? `<span class="gtm-funnel-arrow">›</span>` : ""}
      <span class="gtm-funnel-value">${step.value}</span>
      <span class="gtm-funnel-label">${step.label}</span>
      ${step.pctVal ? `<span class="gtm-funnel-pct">${step.pctVal}</span>` : ""}
    </div>
  `;

  return `
    <div class="gtm-overview-grid">
      ${topCards.map((c) => `
        <div class="gtm-stat-card">
          <p class="gtm-stat-value">${c.value}</p>
          <p class="gtm-stat-label">${c.label}</p>
          ${c.sub ? `<p class="gtm-stat-sub">${c.sub}</p>` : ""}
        </div>
      `).join("")}
    </div>
    <div class="gtm-funnels">
      <div class="gtm-funnel-row">
        ${citySteps.map((s, i) => renderFunnelStep(s, i === 0)).join("")}
      </div>
      <div class="gtm-funnel-row">
        ${countySteps.map((s, i) => renderFunnelStep(s, i === 0)).join("")}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Jurisdiction table (cities / counties)
// ---------------------------------------------------------------------------

function renderJurisdictionTable(rows: GtmCityRow[], showCounty: boolean): string {
  const query = filterQuery.toLowerCase();
  const filtered = query
    ? rows.filter((r) => r.name.toLowerCase().includes(query) || r.copo.toLowerCase().includes(query))
    : rows;

  if (!filtered.length) {
    return `<p class="gtm-empty">No results for "${filterQuery}".</p>`;
  }

  const countyCol = showCounty ? `<th>County</th>` : "";

  const rowsHtml = filtered.map((r) => {
    const countyCell = showCounty ? `<td>${r.county_name ?? "—"}</td>` : "";
    const revenue = r.latest_revenue != null ? formatCompactCurrency(r.latest_revenue) : "—";
    const dataDate = r.latest_data_date ? r.latest_data_date.slice(0, 7) : "—";
    return `
      <tr>
        <td class="gtm-col-name">${r.name}</td>
        <td class="gtm-col-copo">${r.copo}</td>
        ${countyCell}
        <td class="gtm-col-center">${coverageBadge(r.contact_count)}</td>
        <td class="gtm-col-center">${coverageBadge(r.email_count)}</td>
        <td class="gtm-col-center">${coverageBadge(r.phone_count)}</td>
        <td class="gtm-col-center">${coverageBadge(r.user_count)}</td>
        <td class="gtm-col-center">${dataDate}</td>
        <td class="gtm-col-right">${revenue}</td>
      </tr>
    `;
  }).join("");

  return `
    <p class="gtm-row-count">${filtered.length} of ${rows.length} shown</p>
    <div class="gtm-table-wrapper">
      <table class="gtm-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>COPO</th>
            ${countyCol}
            <th class="gtm-col-center">Contacts</th>
            <th class="gtm-col-center">Emails</th>
            <th class="gtm-col-center">Phones</th>
            <th class="gtm-col-center">Users</th>
            <th class="gtm-col-center">Latest Data</th>
            <th class="gtm-col-right">Latest Revenue</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Users table
// ---------------------------------------------------------------------------

function renderUsersTable(data: GtmUsersResponse): string {
  const query = filterQuery.toLowerCase();
  const filtered = query
    ? data.users.filter((u) =>
        u.email.toLowerCase().includes(query) ||
        (u.display_name ?? "").toLowerCase().includes(query) ||
        (u.jurisdiction_name ?? "").toLowerCase().includes(query),
      )
    : data.users;

  if (!filtered.length) {
    return `<p class="gtm-empty">No users found.</p>`;
  }

  const rowsHtml = filtered.map((u) => {
    const created = u.created_at.slice(0, 10);
    const lastLogin = u.last_login_at ? u.last_login_at.slice(0, 10) : "—";
    const statusClass = u.status === "active" ? "gtm-badge--ok" : "gtm-badge--none";
    return `
      <tr>
        <td>${u.email}</td>
        <td>${u.display_name ?? "—"}</td>
        <td>${u.job_title ?? "—"}</td>
        <td>${u.jurisdiction_name ?? "—"}</td>
        <td class="gtm-col-center"><span class="gtm-badge ${statusClass}">${u.status}</span></td>
        <td class="gtm-col-center">${created}</td>
        <td class="gtm-col-center">${lastLogin}</td>
      </tr>
    `;
  }).join("");

  return `
    <p class="gtm-row-count">${filtered.length} of ${data.total} shown</p>
    <div class="gtm-table-wrapper">
      <table class="gtm-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Title</th>
            <th>Jurisdiction</th>
            <th class="gtm-col-center">Status</th>
            <th class="gtm-col-center">Created</th>
            <th class="gtm-col-center">Last Login</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Contacts table
// ---------------------------------------------------------------------------

function renderContactsTable(data: GtmContactsResponse): string {
  if (!data.contacts.length) {
    return filterQuery
      ? `<p class="gtm-empty">No contacts match "${filterQuery}".</p>`
      : `<p class="gtm-empty">No contacts loaded.</p>`;
  }

  function emailCell(row: GtmContactRow): string {
    if (!row.email) return "—";
    return `<a href="mailto:${row.email}" class="gtm-email-link">${row.email}</a>`;
  }

  const rowsHtml = data.contacts.map((c) => `
    <tr>
      <td class="gtm-col-name">${c.jurisdiction_name}</td>
      <td class="gtm-col-center">
        <span class="gtm-badge ${c.jurisdiction_type === "city" ? "gtm-badge--ok" : "gtm-badge--county"}">
          ${c.jurisdiction_type}
        </span>
      </td>
      <td>${c.office_title ?? "—"}</td>
      <td>${c.person_name ?? "—"}</td>
      <td>${c.phone ?? "—"}</td>
      <td>${emailCell(c)}</td>
      <td>${c.contact_type ?? "—"}</td>
      <td class="gtm-col-center">${c.verified_date ? c.verified_date.slice(0, 10) : "—"}</td>
    </tr>
  `).join("");

  return `
    <p class="gtm-row-count">${data.total} contacts${filterQuery ? ` matching "${filterQuery}"` : ""}</p>
    <div class="gtm-table-wrapper">
      <table class="gtm-table">
        <thead>
          <tr>
            <th>Jurisdiction</th>
            <th class="gtm-col-center">Type</th>
            <th>Office / Title</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Email</th>
            <th>Contact Type</th>
            <th class="gtm-col-center">Verified</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Tab rendering
// ---------------------------------------------------------------------------

function renderTabContent(container: HTMLElement): void {
  const contentEl = container.querySelector<HTMLElement>(".gtm-tab-content");
  if (!contentEl) return;

  if (activeTab === "cities" && pipelineData) {
    contentEl.innerHTML = renderJurisdictionTable(pipelineData.cities, true);
  } else if (activeTab === "counties" && pipelineData) {
    contentEl.innerHTML = renderJurisdictionTable(pipelineData.counties, false);
  } else if (activeTab === "users" && usersData) {
    contentEl.innerHTML = renderUsersTable(usersData);
  } else if (activeTab === "contacts") {
    if (contactsData) {
      contentEl.innerHTML = renderContactsTable(contactsData);
    } else {
      contentEl.innerHTML = `<div class="loading-spinner"></div>`;
    }
  } else {
    contentEl.innerHTML = `<div class="loading-spinner"></div>`;
  }
}

function updateTabButtons(container: HTMLElement): void {
  container.querySelectorAll<HTMLButtonElement>(".gtm-tab-btn").forEach((btn) => {
    const tab = btn.dataset.tab as ActiveTab;
    btn.classList.toggle("is-active", tab === activeTab);
  });
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadPipelineAndUsers(container: HTMLElement): Promise<void> {
  try {
    pipelineData = await getGtmPipeline();
    const statsEl = container.querySelector<HTMLElement>(".gtm-stats-placeholder");
    if (statsEl) statsEl.innerHTML = renderStatsCards(pipelineData.stats);
    renderTabContent(container);
  } catch (err) {
    const contentEl = container.querySelector<HTMLElement>(".gtm-tab-content");
    if (contentEl) {
      contentEl.innerHTML = `<p class="error-message">Failed to load pipeline data: ${err instanceof Error ? err.message : String(err)}</p>`;
    }
  }

  try {
    usersData = await getGtmUsers();
    if (activeTab === "users") renderTabContent(container);
    const usersBtn = container.querySelector<HTMLButtonElement>('[data-tab="users"]');
    if (usersBtn && usersData) usersBtn.textContent = `Users (${usersData.total})`;
  } catch {
    /* secondary; ignore */
  }
}

async function loadContacts(container: HTMLElement): Promise<void> {
  const contentEl = container.querySelector<HTMLElement>(".gtm-tab-content");
  if (contentEl && activeTab === "contacts") {
    contentEl.innerHTML = `<div class="loading-spinner"></div>`;
  }
  try {
    contactsData = await getGtmContacts(filterQuery);
    if (activeTab === "contacts") renderTabContent(container);
    const contactsBtn = container.querySelector<HTMLButtonElement>('[data-tab="contacts"]');
    if (contactsBtn && contactsData) contactsBtn.textContent = `Contacts (${contactsData.total})`;
  } catch (err) {
    if (contentEl && activeTab === "contacts") {
      contentEl.innerHTML = `<p class="error-message">Failed to load contacts: ${err instanceof Error ? err.message : String(err)}</p>`;
    }
  }
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export const gtmView: View = {
  render(container: HTMLElement): void {
    _container = container;
    activeTab = "cities";
    pipelineData = null;
    usersData = null;
    contactsData = null;
    filterQuery = "";

    const now = new Date();
    const defaultYear = now.getFullYear();
    const defaultMonth = now.getMonth() + 1;

    container.innerHTML = `
      <div class="view-header">
        <h1 class="view-title">Admin Dashboard</h1>
        <p class="view-subtitle">Go-to-market pipeline · Users · Contacts across all Oklahoma municipalities.</p>
      </div>

      <div class="gtm-stats-placeholder">
        <div class="loading-spinner"></div>
      </div>

      <div class="panel gtm-send-panel">
        <h2 class="panel-title">Send Report Emails</h2>
        <p class="panel-desc">
          Sends each active user a personalized city revenue email with a one-click
          magic-link to their report page.
        </p>
        <div class="gtm-send-form">
          <label class="form-label">
            Year
            <input class="form-input gtm-send-year" type="number" min="2020" max="2100" value="${defaultYear}" />
          </label>
          <label class="form-label">
            Month
            <select class="form-select gtm-send-month">
              ${["January","February","March","April","May","June","July","August","September","October","November","December"]
                .map((m, i) => `<option value="${i + 1}"${i + 1 === defaultMonth ? " selected" : ""}>${m}</option>`)
                .join("")}
            </select>
          </label>
          <button class="button button--primary gtm-send-btn" type="button">Send Campaign</button>
        </div>
        <p class="gtm-send-status"></p>
      </div>

      <div class="gtm-controls">
        <div class="gtm-tabs">
          <button class="gtm-tab-btn is-active" data-tab="cities">Cities</button>
          <button class="gtm-tab-btn" data-tab="counties">Counties</button>
          <button class="gtm-tab-btn" data-tab="users">Users</button>
          <button class="gtm-tab-btn" data-tab="contacts">Contacts</button>
        </div>
        <input
          class="gtm-search"
          type="search"
          placeholder="Filter by name…"
          aria-label="Filter rows"
        />
      </div>

      <div class="gtm-tab-content">
        <div class="loading-spinner"></div>
      </div>
    `;

    // Wire tabs
    container.querySelectorAll<HTMLButtonElement>(".gtm-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.dataset.tab as ActiveTab;
        updateTabButtons(container);

        // Contacts tab: trigger server search
        if (activeTab === "contacts" && !contactsData) {
          void loadContacts(container);
        } else {
          renderTabContent(container);
        }
      });
    });

    // Wire search
    const searchEl = container.querySelector<HTMLInputElement>(".gtm-search");
    if (searchEl) {
      searchEl.addEventListener("input", () => {
        filterQuery = searchEl.value.trim();

        if (activeTab === "contacts") {
          // Debounce server search for contacts tab
          if (contactsSearchDebounce) clearTimeout(contactsSearchDebounce);
          contactsSearchDebounce = setTimeout(() => {
            contactsData = null;
            void loadContacts(container);
          }, 400);
        } else {
          renderTabContent(container);
        }
      });
    }

    // Wire send campaign
    const sendBtn = container.querySelector<HTMLButtonElement>(".gtm-send-btn");
    const sendStatus = container.querySelector<HTMLElement>(".gtm-send-status");
    sendBtn?.addEventListener("click", () => {
      const yearEl = container.querySelector<HTMLInputElement>(".gtm-send-year");
      const monthEl = container.querySelector<HTMLSelectElement>(".gtm-send-month");
      const year = parseInt(yearEl?.value ?? "0", 10);
      const month = parseInt(monthEl?.value ?? "0", 10);
      if (!year || !month) return;

      if (sendStatus) sendStatus.textContent = "Queuing…";
      if (sendBtn) sendBtn.disabled = true;

      sendGtmReports(year, month)
        .then((res) => {
          if (sendStatus) {
            sendStatus.textContent = `✓ Campaign queued for ${res.period}. Emails are sending in the background.`;
            sendStatus.style.color = "var(--success, #16a34a)";
          }
        })
        .catch((err: unknown) => {
          if (sendStatus) {
            sendStatus.textContent = `Error: ${err instanceof Error ? err.message : String(err)}`;
            sendStatus.style.color = "var(--error, #dc2626)";
          }
        })
        .finally(() => {
          if (sendBtn) sendBtn.disabled = false;
        });
    });

    // Auth guard: must be admin
    refreshSession().then((session) => {
      if (!session.authenticated || !session.user?.is_admin) {
        navigateTo(ROUTES.login, { replace: true });
        return;
      }
      void loadPipelineAndUsers(container);
    });
  },

  destroy(): void {
    _container = null;
    pipelineData = null;
    usersData = null;
    contactsData = null;
    if (contactsSearchDebounce) clearTimeout(contactsSearchDebounce);
  },
};
