#!/usr/bin/env python3
"""
Contact enrichment pipeline for MuniRevenue.

Three enrichment tiers (run independently):

  python scripts/enrich_contacts.py scrape   -- Tier 1: scrape source_url pages for mailto/tel
  python scripts/enrich_contacts.py infer    -- Tier 2: infer email patterns from existing data
  python scripts/enrich_contacts.py dork     -- Tier 5: generate Google search queries
  python scripts/enrich_contacts.py report   -- summary of enrichment gaps

Results written to data/enrichment/ as CSV files for human review before import.
"""
import argparse
import asyncio
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/munirev")
OUT_DIR = Path(__file__).parent.parent / "data" / "enrichment"

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)


async def fetch_all_contacts(conn):
    """Return all contacts as list of dicts."""
    rows = await conn.fetch("""
        SELECT id, jurisdiction_type, jurisdiction_name, person_name,
               office_title, phone, email, source_url, contact_type
        FROM contacts
        ORDER BY jurisdiction_name, id
    """)
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Tier 1: Source URL scraper
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"
)
# Filter out common false-positive email patterns
EMAIL_BLACKLIST = {
    "example.com", "sentry.io", "wixpress.com", "w3.org",
    "schema.org", "ogp.me", "facebook.com", "twitter.com",
    "google.com", "googleapis.com", "gstatic.com", "cloudflare.com",
}


def is_valid_scraped_email(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    if domain in EMAIL_BLACKLIST:
        return False
    # Skip image/file references mistakenly captured
    if any(email.lower().endswith(ext) for ext in (".png", ".jpg", ".gif", ".svg")):
        return False
    return True


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


async def scrape_url(session, url: str, timeout: float = 15.0) -> tuple[set[str], set[str]]:
    """Fetch a URL and extract emails and phones from the HTML."""
    import aiohttp

    emails, phones = set(), set()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout),
                               allow_redirects=True, ssl=False) as resp:
            if resp.status != 200:
                return emails, phones
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                return emails, phones
            text = await resp.text(errors="replace")
    except Exception:
        return emails, phones

    for m in EMAIL_RE.finditer(text):
        email = m.group(0).lower().rstrip(".")
        if is_valid_scraped_email(email):
            emails.add(email)

    for m in PHONE_RE.finditer(text):
        p = normalize_phone(m.group(0))
        if p:
            phones.add(p)

    return emails, phones


async def run_scrape():
    """Scrape source URLs for all contacts, write discovered info to CSV."""
    try:
        import aiohttp
    except ImportError:
        print("ERROR: aiohttp is required. Install with: pip install aiohttp")
        sys.exit(1)

    conn = await get_connection()
    contacts = await fetch_all_contacts(conn)
    await conn.close()

    # Group contacts by source_url to dedupe requests
    url_contacts: dict[str, list[dict]] = defaultdict(list)
    for c in contacts:
        if c["source_url"]:
            url_contacts[c["source_url"]].append(c)

    print(f"Scraping {len(url_contacts)} unique source URLs...")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outpath = OUT_DIR / "scraped_findings.csv"

    results = []
    sem = asyncio.Semaphore(5)  # max 5 concurrent requests

    async def scrape_one(session, url, contact_list):
        async with sem:
            emails, phones = await scrape_url(session, url)
            for c in contact_list:
                # Only report NEW findings (not already in the contact record)
                existing_email = (c["email"] or "").lower()
                existing_phone = normalize_phone(c["phone"]) if c["phone"] else None
                new_emails = {e for e in emails if e != existing_email}
                new_phones = {p for p in phones if p != existing_phone}
                if new_emails or new_phones:
                    results.append({
                        "contact_id": c["id"],
                        "jurisdiction_name": c["jurisdiction_name"],
                        "person_name": c["person_name"],
                        "existing_email": c["email"] or "",
                        "existing_phone": c["phone"] or "",
                        "found_emails": "; ".join(sorted(new_emails)),
                        "found_phones": "; ".join(sorted(new_phones)),
                        "source_url": url,
                    })

    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "MuniRevenue Contact Enrichment/1.0"}
    ) as session:
        tasks = []
        for url, clist in url_contacts.items():
            tasks.append(scrape_one(session, url, clist))

        done = 0
        # Process in batches for progress reporting
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            await asyncio.gather(*batch)
            done += len(batch)
            print(f"  Progress: {done}/{len(tasks)} URLs scraped")

    # Write results
    if results:
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contact_id", "jurisdiction_name", "person_name",
                "existing_email", "existing_phone",
                "found_emails", "found_phones", "source_url",
            ])
            writer.writeheader()
            writer.writerows(results)
        print(f"\nWrote {len(results)} findings to {outpath}")
    else:
        print("\nNo new contact info found from source URLs.")


# ---------------------------------------------------------------------------
# Tier 2: Domain pattern inference
# ---------------------------------------------------------------------------

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def clean_name_parts(name: str) -> tuple[str, str] | None:
    """Extract (first, last) from a name, stripping suffixes like Jr./Sr."""
    parts = name.lower().split()
    # Strip trailing suffixes
    while len(parts) > 1 and parts[-1] in NAME_SUFFIXES:
        parts.pop()
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


def extract_patterns(emails: list[str], names: list[str | None]) -> list[str]:
    """Given known emails+names for a jurisdiction, infer naming patterns.

    Returns pattern strings like:
        'first.last'   → john.smith@domain
        'firstlast'    → johnsmith@domain
        'first_last'   → john_smith@domain
        'flast'         → jsmith@domain
        'firstl'        → johns@domain
        'first'         → john@domain
    """
    patterns = []
    for email, name in zip(emails, names):
        if not name or "@" not in email:
            continue
        local = email.split("@")[0].lower()
        cleaned = clean_name_parts(name)
        if not cleaned:
            continue
        first, last = cleaned

        if local == f"{first}.{last}":
            patterns.append("first.last")
        elif local == f"{first}{last}":
            patterns.append("firstlast")
        elif local == f"{first}_{last}":
            patterns.append("first_last")
        elif local == f"{first[0]}{last}":
            patterns.append("flast")
        elif local == f"{first}{last[0]}":
            patterns.append("firstl")
        elif local == first:
            patterns.append("first")
        elif local == f"{last}.{first}":
            patterns.append("last.first")
        elif local == f"{first[0]}.{last}":
            patterns.append("f.last")

    return patterns


def generate_candidate(pattern: str, name: str, domain: str) -> str | None:
    cleaned = clean_name_parts(name)
    if not cleaned:
        return None
    first, last = cleaned

    local = {
        "first.last": f"{first}.{last}",
        "firstlast": f"{first}{last}",
        "first_last": f"{first}_{last}",
        "flast": f"{first[0]}{last}",
        "firstl": f"{first}{last[0]}",
        "first": first,
        "last.first": f"{last}.{first}",
        "f.last": f"{first[0]}.{last}",
    }.get(pattern)

    if not local:
        return None
    return f"{local}@{domain}"


async def run_infer():
    """Infer email patterns from existing contacts, suggest candidates."""
    conn = await get_connection()
    contacts = await fetch_all_contacts(conn)
    await conn.close()

    # Group by jurisdiction
    by_jur: dict[str, list[dict]] = defaultdict(list)
    for c in contacts:
        by_jur[c["jurisdiction_name"]].append(c)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outpath = OUT_DIR / "inferred_emails.csv"
    results = []

    for jur_name, jur_contacts in sorted(by_jur.items()):
        # Collect known emails and their person names
        known_emails = []
        known_names = []
        # Track which domain(s) this jurisdiction uses (exclude personal domains)
        personal_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                          "aol.com", "att.net", "sbcglobal.net", "cox.net",
                          "icloud.com", "me.com", "live.com", "msn.com",
                          "pldi.net", "suddenlink.net", "windstream.net",
                          "valornet.com", "pistbb.com", "cableone.net",
                          "fullspectrum.net"}
        domain_counts: dict[str, int] = defaultdict(int)

        for c in jur_contacts:
            if c["email"] and c["person_name"]:
                known_emails.append(c["email"].lower())
                known_names.append(c["person_name"])
                domain = c["email"].split("@")[-1].lower()
                if domain not in personal_domains:
                    domain_counts[domain] += 1

        if not domain_counts:
            continue  # No official domain found

        # Pick the most common official domain
        official_domain = max(domain_counts, key=domain_counts.get)
        if domain_counts[official_domain] < 2:
            continue  # Need at least 2 emails on the same domain to establish a pattern

        # Extract patterns from known emails on this domain
        domain_emails = []
        domain_names = []
        for em, nm in zip(known_emails, known_names):
            if em.split("@")[-1].lower() == official_domain:
                domain_emails.append(em)
                domain_names.append(nm)

        patterns = extract_patterns(domain_emails, domain_names)
        if not patterns:
            continue

        # Find the dominant pattern
        from collections import Counter
        pattern_counts = Counter(patterns)
        dominant_pattern = pattern_counts.most_common(1)[0][0]
        confidence = pattern_counts[dominant_pattern] / len(patterns)

        # Generate candidates for contacts missing emails
        for c in jur_contacts:
            if c["email"]:
                continue  # Already has email
            if not c["person_name"]:
                continue  # Can't generate without a name

            candidate = generate_candidate(dominant_pattern, c["person_name"], official_domain)
            if candidate:
                results.append({
                    "contact_id": c["id"],
                    "jurisdiction_name": jur_name,
                    "person_name": c["person_name"],
                    "office_title": c["office_title"] or "",
                    "inferred_email": candidate,
                    "pattern": dominant_pattern,
                    "domain": official_domain,
                    "confidence": f"{confidence:.0%}",
                    "sample_count": len(domain_emails),
                })

    if results:
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contact_id", "jurisdiction_name", "person_name", "office_title",
                "inferred_email", "pattern", "domain", "confidence", "sample_count",
            ])
            writer.writeheader()
            writer.writerows(results)
        print(f"Wrote {len(results)} inferred email candidates to {outpath}")
    else:
        print("No email patterns could be inferred.")


# ---------------------------------------------------------------------------
# Tier 5: Google dorking query generator
# ---------------------------------------------------------------------------

async def run_dork():
    """Generate Google search queries for contacts missing emails."""
    conn = await get_connection()
    contacts = await fetch_all_contacts(conn)
    await conn.close()

    # Group by jurisdiction, find those with no emails at all
    by_jur: dict[str, list[dict]] = defaultdict(list)
    for c in contacts:
        by_jur[c["jurisdiction_name"]].append(c)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outpath = OUT_DIR / "google_dork_queries.csv"
    results = []

    for jur_name, jur_contacts in sorted(by_jur.items()):
        has_any_email = any(c["email"] for c in jur_contacts)
        jur_type = jur_contacts[0]["jurisdiction_type"]

        # For jurisdictions with no emails, generate broad queries
        if not has_any_email:
            # Query 1: site-specific email search
            source_urls = {c["source_url"] for c in jur_contacts if c["source_url"]}
            domains = set()
            for u in source_urls:
                parsed = urlparse(u)
                if parsed.hostname:
                    domains.add(parsed.hostname)

            for domain in domains:
                results.append({
                    "jurisdiction_name": jur_name,
                    "jurisdiction_type": jur_type,
                    "query_type": "site_email",
                    "query": f'site:{domain} "@" email',
                    "priority": "high",
                })

            # Query 2: general contact page search
            label = "city of" if jur_type == "city" else ""
            results.append({
                "jurisdiction_name": jur_name,
                "jurisdiction_type": jur_type,
                "query_type": "contact_page",
                "query": f'"{label} {jur_name}" Oklahoma contact email clerk',
                "priority": "high",
            })

            # Query 3: staff directory search
            results.append({
                "jurisdiction_name": jur_name,
                "jurisdiction_type": jur_type,
                "query_type": "staff_directory",
                "query": f'"{label} {jur_name}" Oklahoma "staff directory" OR "employee directory"',
                "priority": "medium",
            })

        # For specific contacts without email but with a name
        for c in jur_contacts:
            if c["email"] or not c["person_name"]:
                continue
            title = c["office_title"] or ""
            results.append({
                "jurisdiction_name": jur_name,
                "jurisdiction_type": jur_type,
                "query_type": "person_search",
                "query": f'"{c["person_name"]}" {title} "{jur_name}" Oklahoma email',
                "priority": "low" if has_any_email else "medium",
            })

    if results:
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "jurisdiction_name", "jurisdiction_type",
                "query_type", "query", "priority",
            ])
            writer.writeheader()
            writer.writerows(results)
        print(f"Wrote {len(results)} search queries to {outpath}")
        # Summary
        from collections import Counter
        by_type = Counter(r["query_type"] for r in results)
        by_priority = Counter(r["priority"] for r in results)
        print(f"  By type: {dict(by_type)}")
        print(f"  By priority: {dict(by_priority)}")
    else:
        print("All contacts already have emails.")


# ---------------------------------------------------------------------------
# Report: enrichment gap summary
# ---------------------------------------------------------------------------

async def run_report():
    """Print a summary of contact enrichment gaps."""
    conn = await get_connection()
    contacts = await fetch_all_contacts(conn)
    await conn.close()

    total = len(contacts)
    with_email = sum(1 for c in contacts if c["email"])
    with_phone = sum(1 for c in contacts if c["phone"])
    with_source = sum(1 for c in contacts if c["source_url"])

    by_jur: dict[str, list[dict]] = defaultdict(list)
    for c in contacts:
        by_jur[c["jurisdiction_name"]].append(c)

    jur_no_email = sum(1 for cs in by_jur.values() if not any(c["email"] for c in cs))
    jur_partial = sum(1 for cs in by_jur.values()
                      if any(c["email"] for c in cs) and any(not c["email"] for c in cs))

    print("=" * 60)
    print("CONTACT ENRICHMENT GAP REPORT")
    print("=" * 60)
    print(f"\nTotal contacts:           {total}")
    print(f"With email:               {with_email} ({with_email/total:.0%})")
    print(f"Without email:            {total - with_email} ({(total-with_email)/total:.0%})")
    print(f"With phone:               {with_phone} ({with_phone/total:.0%})")
    print(f"With source URL:          {with_source} ({with_source/total:.0%})")
    print(f"\nTotal jurisdictions:       {len(by_jur)}")
    print(f"Zero emails:              {jur_no_email}")
    print(f"Partial emails:           {jur_partial}")
    print(f"Full coverage:            {len(by_jur) - jur_no_email - jur_partial}")

    # Domain analysis
    from collections import Counter
    domains = Counter()
    personal = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                "aol.com", "att.net", "sbcglobal.net", "cox.net",
                "icloud.com", "me.com", "live.com", "msn.com",
                "pldi.net", "suddenlink.net", "windstream.net"}
    official_count = 0
    personal_count = 0
    for c in contacts:
        if c["email"]:
            d = c["email"].split("@")[-1].lower()
            domains[d] += 1
            if d in personal:
                personal_count += 1
            else:
                official_count += 1

    print(f"\nEmail breakdown:")
    print(f"  Official domain:        {official_count}")
    print(f"  Personal domain:        {personal_count}")
    print(f"  Unique domains:         {len(domains)}")

    # Enrichment potential
    print(f"\nEnrichment potential:")
    print(f"  Tier 1 (scrape):        {with_source} contacts have source URLs")
    print(f"  Tier 2 (infer):         {jur_partial} jurisdictions have partial coverage")
    print(f"  Tier 5 (search):        {jur_no_email} jurisdictions need manual search")

    # Check for existing enrichment files
    if OUT_DIR.exists():
        print(f"\nExisting enrichment files in {OUT_DIR}:")
        for f in sorted(OUT_DIR.iterdir()):
            if f.is_file():
                lines = sum(1 for _ in open(f)) - 1  # subtract header
                print(f"  {f.name}: {lines} rows")


# ---------------------------------------------------------------------------
# Apply: import reviewed enrichment data back into contacts
# ---------------------------------------------------------------------------

async def run_apply(filepath: str):
    """Apply reviewed enrichment CSV back to the contacts table.

    Expects a CSV with at minimum: contact_id, and one or more of:
    new_email, new_phone. Rows without these columns are skipped.
    """
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    conn = await get_connection()
    updated_email = 0
    updated_phone = 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contact_id = int(row["contact_id"])

            # Apply email if present and column exists
            new_email = row.get("new_email", "").strip() or row.get("inferred_email", "").strip()
            if new_email:
                await conn.execute("""
                    UPDATE contacts
                    SET email = $1, updated_at = now()
                    WHERE id = $2 AND (email IS NULL OR email = '')
                """, new_email, contact_id)
                updated_email += 1

            # Apply phone if present
            new_phone = row.get("new_phone", "").strip() or row.get("found_phones", "").strip()
            if new_phone:
                # Take first phone if multiple separated by semicolons
                first_phone = new_phone.split(";")[0].strip()
                await conn.execute("""
                    UPDATE contacts
                    SET phone = $1, updated_at = now()
                    WHERE id = $2 AND (phone IS NULL OR phone = '')
                """, first_phone, contact_id)
                updated_phone += 1

    await conn.close()
    print(f"Applied: {updated_email} emails, {updated_phone} phones updated")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Contact enrichment pipeline for MuniRevenue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scrape", help="Tier 1: scrape source URLs for emails/phones")
    sub.add_parser("infer", help="Tier 2: infer email patterns from existing data")
    sub.add_parser("dork", help="Tier 5: generate Google search queries")
    sub.add_parser("report", help="Show enrichment gap summary")

    apply_p = sub.add_parser("apply", help="Import reviewed enrichment CSV into contacts")
    apply_p.add_argument("file", help="Path to the reviewed CSV file")

    args = parser.parse_args()

    if args.command == "scrape":
        asyncio.run(run_scrape())
    elif args.command == "infer":
        asyncio.run(run_infer())
    elif args.command == "dork":
        asyncio.run(run_dork())
    elif args.command == "report":
        asyncio.run(run_report())
    elif args.command == "apply":
        asyncio.run(run_apply(args.file))


if __name__ == "__main__":
    main()
