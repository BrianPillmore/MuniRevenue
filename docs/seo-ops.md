# SEO Operations Checklist

## Goal

Turn the SEO surface into a monitored production workflow after deployment.

## Google Search Console

1. Verify the `munirevenue.com` domain property.
2. Submit `https://munirevenue.com/sitemap.xml`.
3. Confirm that these page classes begin indexing:
   - `/`
   - `/oklahoma-cities`
   - `/oklahoma-counties`
   - `/oklahoma-cities/{slug}`
   - `/oklahoma-counties/{slug}`
   - `/insights/anomalies`
   - `/insights/missed-filings`
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

## Metrics To Watch

- indexed page count
- query impressions
- click-through rate
- top-performing city pages
- top-performing county pages
- anomaly and missed-filings explainer impressions
- duplicate-title or duplicate-canonical warnings

## Notes

- The generated SEO pages are build artifacts, so the frontend build step must run before deploy.
- Search Console and Bing verification cannot be completed from the repo alone; they require the production property owner account.
