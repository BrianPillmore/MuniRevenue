/* ══════════════════════════════════════════════
   History API router
   ══════════════════════════════════════════════ */

import { refreshSession } from "./auth";
import { canonicalizePath, loginPath, normalizePathname, routeFromLegacyHash, ROUTES } from "./paths";
import type { View } from "./types";

interface Route {
  /** Pattern like "/city/:copo" — segments starting with ":" are params */
  pattern: string;
  view: View;
}

interface MatchResult {
  view: View;
  params: Record<string, string>;
}

interface NavigateOptions {
  replace?: boolean;
}

let routes: Route[] = [];
let currentView: View | null = null;
let container: HTMLElement | null = null;
let initialized = false;
let renderSequence = 0;

function splitSegments(path: string): string[] {
  return canonicalizePath(path).split("/");
}

function toNavigableUrl(value: string): { pathname: string; url: string } {
  const resolved = new URL(value, window.location.origin);
  const pathname = canonicalizePath(resolved.pathname || ROUTES.overview);
  const search = resolved.search || "";
  return {
    pathname,
    url: `${pathname}${search}`,
  };
}

/**
 * Try to match a path string against registered route patterns.
 * Returns the matched view and extracted params, or null if no match.
 */
function matchRoute(path: string): MatchResult | null {
  const pathParts = splitSegments(path);

  for (const route of routes) {
    const patternParts = splitSegments(route.pattern);

    if (patternParts.length !== pathParts.length) continue;

    const params: Record<string, string> = {};
    let matched = true;

    for (let index = 0; index < patternParts.length; index += 1) {
      if (patternParts[index].startsWith(":")) {
        params[patternParts[index].slice(1)] = decodeURIComponent(pathParts[index]);
      } else if (patternParts[index] !== pathParts[index]) {
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

function redirectLegacyHashRoute(): boolean {
  const translated = routeFromLegacyHash(window.location.hash);
  if (!translated) return false;

  history.replaceState(null, "", translated);
  return true;
}

function maybeCanonicalizeCurrentPath(): boolean {
  const current = normalizePathname(window.location.pathname);
  const canonical = canonicalizePath(current);

  if (current !== canonical) {
    history.replaceState(null, "", canonical);
    return true;
  }

  return false;
}

function isProtectedPath(path: string): boolean {
  const protectedBases = [ROUTES.account, ROUTES.forecast, ROUTES.anomalies, ROUTES.missedFilings, ROUTES.trends, ROUTES.rankings, ROUTES.gtm];
  return protectedBases.some((base) => path === base || path.startsWith(`${base}/`));
}

export function protectedRouteRedirectTarget(
  requestedPath: string,
  authenticated: boolean,
): string | null {
  const resolved = new URL(requestedPath, window.location.origin);
  const normalized = canonicalizePath(resolved.pathname);
  if (!isProtectedPath(normalized) || authenticated) {
    return null;
  }
  return loginPath(`${normalized}${resolved.search || ""}`);
}

async function renderRoute(): Promise<void> {
  if (!container) return;
  const sequence = ++renderSequence;

  if (redirectLegacyHashRoute()) {
    window.scrollTo({ top: 0 });
  }
  maybeCanonicalizeCurrentPath();

  const path = canonicalizePath(window.location.pathname || ROUTES.overview);
  if (isProtectedPath(path)) {
    const requestedPath = `${path}${window.location.search || ""}`;
    const session = await refreshSession();
    if (sequence !== renderSequence) return;
    const loginTarget = protectedRouteRedirectTarget(requestedPath, session.authenticated);
    if (loginTarget) {
      if (canonicalizePath(window.location.pathname || ROUTES.overview) !== canonicalizePath(ROUTES.login)) {
        navigateTo(loginTarget, { replace: true });
      }
      return;
    }
  }
  const match = matchRoute(path);

  if (currentView) {
    currentView.destroy();
    currentView = null;
  }

  container.innerHTML = "";

  if (match) {
    currentView = match.view;
    match.view.render(container, match.params);
    window.dispatchEvent(new Event("app:navigation"));
  } else {
    navigateTo(ROUTES.overview, { replace: true });
  }
}

function handleLocationChange(): void {
  void renderRoute();
}

function isInterceptableLink(anchor: HTMLAnchorElement): boolean {
  if (anchor.target && anchor.target !== "_self") return false;
  if (anchor.hasAttribute("download")) return false;

  const href = anchor.getAttribute("href");
  if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) return false;

  return true;
}

function handleDocumentClick(event: MouseEvent): void {
  if (event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

  const target = event.target as HTMLElement | null;
  const anchor = target?.closest<HTMLAnchorElement>("a");
  if (!anchor || !isInterceptableLink(anchor)) return;

  const href = anchor.getAttribute("href") ?? "";

  if (href.startsWith("#/")) {
    const translated = routeFromLegacyHash(href);
    if (translated) {
      event.preventDefault();
      navigateTo(translated);
    }
    return;
  }

  if (href.startsWith("#")) return;

  const url = new URL(anchor.href, window.location.origin);
  if (url.origin !== window.location.origin) return;
  if (url.pathname.startsWith("/api")) return;
  if (!matchRoute(url.pathname)) return;

  event.preventDefault();
  navigateTo(`${url.pathname}${url.search}`);
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

  if (!initialized) {
    window.addEventListener("popstate", handleLocationChange);
    window.addEventListener("hashchange", handleLocationChange);
    document.addEventListener("click", handleDocumentClick);
    initialized = true;
  }

  void renderRoute();
}

/**
 * Programmatic navigation.
 */
export function navigateTo(path: string, options: NavigateOptions = {}): void {
  const normalized = toNavigableUrl(path);
  const current = canonicalizePath(window.location.pathname || ROUTES.overview);

  if (normalized.pathname === current && window.location.search === new URL(normalized.url, window.location.origin).search) {
    if (options.replace) {
      history.replaceState(null, "", normalized.url);
    }
    void renderRoute();
    return;
  }

  if (options.replace) {
    history.replaceState(null, "", normalized.url);
  } else {
    history.pushState(null, "", normalized.url);
  }

  window.scrollTo({ top: 0 });
  void renderRoute();
}

/**
 * Get the current path.
 */
export function currentPath(): string {
  return canonicalizePath(window.location.pathname || ROUTES.overview);
}
