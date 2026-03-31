/* ══════════════════════════════════════════════
   Navigation sidebar component
   ══════════════════════════════════════════════ */

import { currentHash } from "../router";

interface NavItem {
  label: string;
  hash: string;
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
      { label: "Overview", hash: "#/overview", icon: "&#9670;" },
      { label: "City Explorer", hash: "#/city", icon: "&#9974;" },
    ],
  },
  {
    heading: "Intelligence",
    items: [
      { label: "Rankings", hash: "#/rankings", icon: "&#9733;" },
      { label: "Trends", hash: "#/trends", icon: "&#8599;" },
    ],
  },
  {
    heading: "Tools",
    items: [
      { label: "About", hash: "#/about", icon: "&#9432;" },
    ],
  },
];

let sidebarEl: HTMLElement | null = null;
let mobileOpen = false;

function isActive(itemHash: string): boolean {
  const current = currentHash();
  /* Exact match or starts with (for parameterized routes like #/city/0955) */
  if (itemHash === "#/city") {
    return current === "#/city" || current.startsWith("#/city/");
  }
  return current === itemHash || current.startsWith(itemHash + "/");
}

function buildSidebarHtml(): string {
  const sectionsHtml = NAV_SECTIONS.map((section) => {
    const itemsHtml = section.items
      .map((item) => {
        const active = isActive(item.hash);
        return `
          <a
            class="sidebar-nav-item${active ? " is-active" : ""}"
            href="${item.hash}"
            data-nav-hash="${item.hash}"
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
        <p class="sidebar-brand-eyebrow">MuniRev</p>
        <p class="sidebar-brand-tagline">Municipal Revenue Intelligence</p>
      </div>
      <nav class="sidebar-nav" aria-label="Main navigation">
        ${sectionsHtml}
      </nav>
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

  /* Update active state on hash change */
  window.addEventListener("hashchange", updateActiveState);
}

/**
 * Update which nav item has the active class.
 */
export function updateActiveState(): void {
  if (!sidebarEl) return;

  sidebarEl.querySelectorAll<HTMLAnchorElement>(".sidebar-nav-item").forEach((link) => {
    const hash = link.dataset.navHash ?? "";
    const active = isActive(hash);
    link.classList.toggle("is-active", active);
    link.setAttribute("aria-current", active ? "page" : "false");
  });
}
