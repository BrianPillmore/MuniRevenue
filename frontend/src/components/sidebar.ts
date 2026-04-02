/* ══════════════════════════════════════════════
   Navigation sidebar component
   ══════════════════════════════════════════════ */

import { currentPath } from "../router";
import { accountPath, isRouteActive, ROUTES } from "../paths";
import { getSessionState, logoutAndRedirect, refreshSession } from "../auth";

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

interface NavSection {
  heading: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    heading: "Explore",
    items: [
      { label: "Overview", href: ROUTES.overview, icon: "&#9670;" },
      { label: "Revenue Explorer", href: ROUTES.city, icon: "&#9974;" },
      { label: "County View", href: ROUTES.county, icon: "&#9962;" },
      { label: "Compare", href: ROUTES.compare, icon: "&#8651;" },
    ],
  },
  {
    heading: "Intelligence",
    items: [
      { label: "Forecasts", href: ROUTES.forecast, icon: "&#8673;" },
      { label: "Anomalies", href: ROUTES.anomalies, icon: "&#9888;" },
      { label: "Missed Filings", href: ROUTES.missedFilings, icon: "&#8709;" },
      { label: "Rankings", href: ROUTES.rankings, icon: "&#9733;" },
      { label: "Trends", href: ROUTES.trends, icon: "&#8599;" },
    ],
  },
  {
    heading: "Tools",
    items: [
      { label: "Export", href: ROUTES.export, icon: "&#8615;" },
      { label: "About", href: ROUTES.about, icon: "&#9432;" },
    ],
  },
];

let sidebarEl: HTMLElement | null = null;
let mobileOpen = false;

function isActive(itemHref: string): boolean {
  return isRouteActive(itemHref, currentPath());
}

function buildSidebarHtml(): string {
  const session = getSessionState();
  const sectionsHtml = NAV_SECTIONS.map((section) => {
    const itemsHtml = section.items
      .map((item) => {
        const active = isActive(item.href);
        return `
          <a
            class="sidebar-nav-item${active ? " is-active" : ""}"
            href="${item.href}"
            data-nav-href="${item.href}"
            aria-current="${active ? "page" : "false"}"
          >
            <span class="sidebar-nav-icon">${item.icon}</span>
            <span class="sidebar-nav-label">${item.label}</span>
          </a>
        `;
      })
      .join("");

    return `
      <div class="sidebar-section">
        <p class="sidebar-section-heading">${section.heading}</p>
        ${itemsHtml}
      </div>
    `;
  }).join("");

  const authHtml = session.authenticated && session.user
    ? `
      <div class="sidebar-auth">
        <p class="sidebar-auth-label">Signed in</p>
        <p class="sidebar-auth-name">${session.user.display_name || session.user.email}</p>
        <div class="sidebar-auth-actions">
          <a class="sidebar-auth-link" href="${accountPath()}">Account</a>
          <button class="sidebar-auth-button" type="button" data-sidebar-logout>Logout</button>
        </div>
      </div>
    `
    : `
      <div class="sidebar-auth">
        <p class="sidebar-auth-label">Account</p>
        <a class="sidebar-auth-link" href="${ROUTES.login}">Login</a>
      </div>
    `;

  return `
    <button
      class="sidebar-hamburger"
      aria-label="Toggle navigation"
      aria-expanded="false"
    >
      <span class="hamburger-bar"></span>
      <span class="hamburger-bar"></span>
      <span class="hamburger-bar"></span>
    </button>
    <div class="sidebar-inner">
      <div class="sidebar-brand">
        <p class="sidebar-brand-eyebrow">MuniRevenue</p>
        <p class="sidebar-brand-tagline">Municipal Revenue Intelligence</p>
      </div>
      <nav class="sidebar-nav" aria-label="Main navigation">
        ${sectionsHtml}
      </nav>
      ${authHtml}
    </div>
  `;
}

function handleMobileToggle(): void {
  if (!sidebarEl) return;
  mobileOpen = !mobileOpen;
  sidebarEl.classList.toggle("is-mobile-open", mobileOpen);
  const btn = sidebarEl.querySelector<HTMLButtonElement>(".sidebar-hamburger");
  if (btn) btn.setAttribute("aria-expanded", String(mobileOpen));
}

function handleNavClick(): void {
  /* Close mobile menu on navigation */
  if (mobileOpen && sidebarEl) {
    mobileOpen = false;
    sidebarEl.classList.remove("is-mobile-open");
    const btn = sidebarEl.querySelector<HTMLButtonElement>(".sidebar-hamburger");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }
}

/**
 * Render the sidebar into the given container element.
 */
export function renderSidebar(container: HTMLElement): void {
  sidebarEl = document.createElement("aside");
  sidebarEl.className = "sidebar";
  sidebarEl.innerHTML = buildSidebarHtml();
  container.appendChild(sidebarEl);

  /* Hamburger toggle */
  const hamburger = sidebarEl.querySelector<HTMLButtonElement>(".sidebar-hamburger");
  hamburger?.addEventListener("click", handleMobileToggle);

  /* Close mobile on nav click */
  sidebarEl.querySelectorAll<HTMLAnchorElement>(".sidebar-nav-item").forEach((link) => {
    link.addEventListener("click", handleNavClick);
  });
  sidebarEl.querySelector<HTMLButtonElement>("[data-sidebar-logout]")
    ?.addEventListener("click", () => {
      void logoutAndRedirect();
    });

  /* Update active state on route changes */
  window.addEventListener("app:navigation", updateActiveState as EventListener);
  window.addEventListener("munirev:auth-changed", rerenderSidebar as EventListener);
  void refreshSession();
}

/**
 * Update which nav item has the active class.
 */
export function updateActiveState(): void {
  if (!sidebarEl) return;

  sidebarEl.querySelectorAll<HTMLAnchorElement>(".sidebar-nav-item").forEach((link) => {
    const href = link.dataset.navHref ?? "";
    const active = isActive(href);
    link.classList.toggle("is-active", active);
    link.setAttribute("aria-current", active ? "page" : "false");
  });
}

function rerenderSidebar(): void {
  if (!sidebarEl) return;
  sidebarEl.innerHTML = buildSidebarHtml();
  const hamburger = sidebarEl.querySelector<HTMLButtonElement>(".sidebar-hamburger");
  hamburger?.addEventListener("click", handleMobileToggle);
  sidebarEl.querySelectorAll<HTMLAnchorElement>(".sidebar-nav-item").forEach((link) => {
    link.addEventListener("click", handleNavClick);
  });
  sidebarEl.querySelector<HTMLButtonElement>("[data-sidebar-logout]")
    ?.addEventListener("click", () => {
      void logoutAndRedirect();
    });
  updateActiveState();
}
