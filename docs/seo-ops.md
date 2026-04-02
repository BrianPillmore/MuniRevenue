# SEO Operations Checklist

## Goal

Operate the public SEO surface as a monitored production workflow.

Important distinction:

- public SEO pages should be indexable
- authenticated app routes should not be treated as SEO landing pages

## Public SEO Targets

Current public/indexable classes:

- `/`
- `/oklahoma-cities`
- `/oklahoma-counties`
- `/oklahoma-cities/{slug}`
- `/oklahoma-counties/{slug}`
- `/insights/anomalies`
- `/insights/missed-filings`
- `robots.txt`
- `sitemap.xml`

Protected app routes such as `/login`, `/account`, `/forecast`, `/anomalies`, and `/missed-filings` are part of the application surface, not the SEO landing-page surface.

## Google Search Console

1. Verify the `munirevenue.com` domain property.
2. Submit `https://munirevenue.com/sitemap.xml`.
3. Confirm indexing begins for the public page classes listed above.
4. Review:
   - indexing status
   - canonical selection
   - crawl errors
   - coverage exclusions
   - top queries
   - top landing pages

## Bing Webmaster Tools

1. Verify the `munirevenue.com` site.
2. Submit `https://munirevenue.com/sitemap.xml`.
3. Monitor crawl coverage and query terms.

## Release Smoke Checks

After each SEO-related deploy, verify:

1. `https://munirevenue.com/`
2. `https://munirevenue.com/oklahoma-cities`
3. `https://munirevenue.com/oklahoma-counties`
4. one generated city page
5. one generated county page
6. `https://munirevenue.com/insights/anomalies`
7. `https://munirevenue.com/insights/missed-filings`
8. `https://munirevenue.com/robots.txt`
9. `https://munirevenue.com/sitemap.xml`

Also verify that protected app pages still behave correctly:

10. `https://munirevenue.com/login`
11. direct navigation to `https://munirevenue.com/forecast`
12. direct navigation to `https://munirevenue.com/anomalies`
13. direct navigation to `https://munirevenue.com/missed-filings`

The goal is to ensure SEO work does not accidentally break auth-routing behavior.

## Metrics To Watch

- indexed page count
- query impressions
- click-through rate
- top-performing city pages
- top-performing county pages
- public explainer-page impressions
- duplicate-title warnings
- duplicate-canonical warnings

## Notes

- generated SEO pages are build artifacts, so the frontend build step must run before deploy
- Search Console and Bing verification require the production property owner account
- the auth-enabled app surface and the public SEO surface should remain intentionally separate
