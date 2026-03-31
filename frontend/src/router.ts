/* ══════════════════════════════════════════════
   Hash-based router
   ══════════════════════════════════════════════ */

import type { View } from "./types";

interface Route {
  /** Pattern like "#/city/:copo" — segments starting with ":" are params */
  pattern: string;
  view: View;
}

interface MatchResult {
  view: View;
  params: Record<string, string>;
}

let routes: Route[] = [];
let currentView: View | null = null;
let container: HTMLElement | null = null;

/**
 * Try to match a hash string against registered route patterns.
 * Returns the matched view and extracted params, or null if no match.
 */
function matchRoute(hash: string): MatchResult | null {
  /* Normalize: strip leading # and trailing slash */
  const path = hash.replace(/^#/, "").replace(/\/$/, "") || "/overview";

  for (const route of routes) {
    const patternPath = route.pattern.replace(/^#/, "");
    const patternParts = patternPath.split("/");
    const pathParts = path.split("/");

    if (patternParts.length !== pathParts.length) continue;

    const params: Record<string, string> = {};
    let matched = true;

    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i].startsWith(":")) {
        params[patternParts[i].slice(1)] = decodeURIComponent(pathParts[i]);
      } else if (patternParts[i] !== pathParts[i]) {
        matched = false;
        break;
      }
    }

    if (matched) {
      return { view: route.view, params };
    }
  }

  return null;
}

/**
 * Handle a hash change: destroy the current view, match the new route,
 * and render the new view into the container.
 */
function onHashChange(): void {
  if (!container) return;

  const hash = window.location.hash || "#/overview";
  const match = matchRoute(hash);

  /* Destroy previous view */
  if (currentView) {
    currentView.destroy();
    currentView = null;
  }

  /* Clear container */
  container.innerHTML = "";

  if (match) {
    currentView = match.view;
    match.view.render(container, match.params);
  } else {
    /* 404: redirect to default */
    navigateTo("#/overview");
  }
}

/**
 * Register route definitions and start listening.
 * @param el The <main> element that views render into.
 * @param routeMap Object mapping pattern strings to View objects.
 */
export function initRouter(
  el: HTMLElement,
  routeMap: Record<string, View>,
): void {
  container = el;
  routes = Object.entries(routeMap).map(([pattern, view]) => ({
    pattern,
    view,
  }));

  window.addEventListener("hashchange", onHashChange);

  /* Initial route */
  onHashChange();
}

/**
 * Programmatic navigation.
 */
export function navigateTo(hash: string): void {
  window.location.hash = hash;
}

/**
 * Get the current hash path.
 */
export function currentHash(): string {
  return window.location.hash || "#/overview";
}
