/* ══════════════════════════════════════════════
   SEO metadata helpers
   ══════════════════════════════════════════════ */

import { canonicalizePath } from "./paths";

const SITE_NAME = "MuniRevenue";
const DEFAULT_TITLE = "MuniRevenue | Municipal Revenue Intelligence";
const DEFAULT_DESCRIPTION =
  "Municipal revenue intelligence for Oklahoma cities and counties, including sales tax trends, use tax analysis, anomalies, forecasts, and missed filing signals.";
const DEFAULT_OG_TYPE = "website";
const SITE_URL =
  (import.meta.env.VITE_SITE_URL as string | undefined) ?? "https://munirevenue.com";

export interface PageMetadata {
  title?: string;
  description?: string;
  path?: string;
  robots?: string;
  ogType?: string;
}

function upsertMeta(
  attributeName: "name" | "property",
  attributeValue: string,
): HTMLMetaElement {
  let element = document.head.querySelector<HTMLMetaElement>(
    `meta[${attributeName}="${attributeValue}"]`,
  );

  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attributeName, attributeValue);
    document.head.appendChild(element);
  }

  return element;
}

function upsertCanonicalLink(): HTMLLinkElement {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');

  if (!element) {
    element = document.createElement("link");
    element.setAttribute("rel", "canonical");
    document.head.appendChild(element);
  }

  return element;
}

function formatTitle(value?: string): string {
  if (!value) return DEFAULT_TITLE;
  if (value.includes(`| ${SITE_NAME}`) || value === DEFAULT_TITLE) return value;
  return `${value} | ${SITE_NAME}`;
}

export function buildCanonicalUrl(path?: string): string {
  const canonicalPath = canonicalizePath(path ?? window.location.pathname);
  return new URL(canonicalPath, SITE_URL).toString();
}

export function setPageMetadata(metadata: PageMetadata = {}): void {
  const title = formatTitle(metadata.title);
  const description = metadata.description ?? DEFAULT_DESCRIPTION;
  const canonicalUrl = buildCanonicalUrl(metadata.path);
  const robots = metadata.robots ?? "index,follow";
  const ogType = metadata.ogType ?? DEFAULT_OG_TYPE;

  document.title = title;

  upsertMeta("name", "description").content = description;
  upsertMeta("name", "robots").content = robots;
  upsertMeta("property", "og:title").content = title;
  upsertMeta("property", "og:description").content = description;
  upsertMeta("property", "og:url").content = canonicalUrl;
  upsertMeta("property", "og:type").content = ogType;
  upsertMeta("property", "og:site_name").content = SITE_NAME;
  upsertMeta("name", "twitter:card").content = "summary_large_image";
  upsertMeta("name", "twitter:title").content = title;
  upsertMeta("name", "twitter:description").content = description;
  upsertCanonicalLink().href = canonicalUrl;
}
