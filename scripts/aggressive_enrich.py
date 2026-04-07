#!/usr/bin/env python3
"""
Aggressive contact enrichment: assign best-available emails from scrape data.

For contacts still missing emails, this script:
1. Looks at ALL emails scraped from their jurisdiction's sites
2. Filters to official-domain emails (not gmail/yahoo/etc)
3. Tries name matching, role matching, then assigns generic contact emails
4. For jurisdictions with a single official email, assigns it to all contacts

Run after scrape and initial apply - this is the "leave no stone unturned" pass.
"""
import asyncio
import csv
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/munirev")
OUT_DIR = Path(__file__).parent.parent / "data" / "enrichment"

PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "att.net", "sbcglobal.net", "cox.net",
    "icloud.com", "me.com", "live.com", "msn.com",
    "pldi.net", "suddenlink.net", "windstream.net",
    "valornet.com", "pistbb.com", "cableone.net",
    "fullspectrum.net", "rocketmail.com", "ymail.com",
    "netzero.net", "earthlink.net", "charter.net",
    "comcast.net", "verizon.net", "bellsouth.net",
}

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}

# Generic role email assignment: office_title keyword -> email local parts
ROLE_MAP = {
    "city clerk": ["cityclerk", "city.clerk", "clerk", "townclerk", "town.clerk"],
    "clerk": ["cityclerk", "city.clerk", "clerk", "townclerk"],
    "treasurer": ["treasurer", "finance", "city.treasurer"],
    "mayor": ["mayor"],
    "city manager": ["citymanager", "city.manager", "manager", "cm"],
    "town manager": ["townmanager", "town.manager", "manager"],
    "administrator": ["admin", "administrator", "cityadmin", "city.admin"],
    "city attorney": ["cityattorney", "city.attorney", "attorney"],
    "police chief": ["policechief", "police.chief", "police", "chief"],
    "fire chief": ["firechief", "fire.chief", "fire"],
    "utilities": ["utilities", "utility", "water", "publicworks"],
    "public works": ["publicworks", "public.works", "pw"],
    "parks": ["parks", "parksandrec", "parks.rec"],
    "council": ["council", "ward"],
}

# Generic contact emails that apply to the whole jurisdiction
GENERIC_LOCALS = {"info", "contact", "contactus", "office", "cityhall",
                  "townhall", "city", "town", "general", "main", "admin"}

# Domains that appear as source_url hosts but aren't actual city/county emails
SCRAPER_FALSE_POSITIVES = {
    "ballotpedia.org", "wikipedia.org", "oklahomawatch.org",
    "oklahoman.com", "tulsaworld.com", "news-star.com",
    "sansoxygen.com", "civicplus.com", "municode.com",
    "revize.com", "boardofdocs.com", "squarespace.com",
    "wix.com", "godaddy.com", "weebly.com", "wordpress.com",
    "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "youtube.com", "nextdoor.com",
    "google.com", "bing.com", "mapquest.com",
    "oklahoma.gov",  # state-level, not jurisdiction
    "ok.gov",
    "constant.com",  # Constant Contact
    "constantcontact.com",
    "mailchimp.com",
    "listserv.com",
    "merchantcircle.com",
    "indiantypefoundry.com",
    "brightok.net",  # ISP
    "pine-net.com",  # ISP
    "coxinet.net",  # ISP
    "tds.net",  # ISP
    "doe.com",  # test/fake
    "atokaokchamber.com",  # chamber of commerce
    "inspiremayescounty.com",  # county tourism
    "elections.ok.gov",  # state elections board
    "visitspirooklahoma.com",  # tourism site
    "pryorchamber.com",  # wrong jurisdiction's chamber
}


def clean_name(name: str) -> tuple[str, str] | None:
    parts = name.lower().split()
    while len(parts) > 1 and parts[-1] in NAME_SUFFIXES:
        parts.pop()
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


def name_matches_email(name: str, email: str) -> bool:
    """Check if a person's name matches an email's local part."""
    cleaned = clean_name(name)
    if not cleaned:
        return False
    first, last = cleaned
    local = email.split("@")[0].lower()
    return (f"{first}.{last}" == local or
            f"{first}{last}" == local or
            f"{first}_{last}" == local or
            f"{first[0]}{last}" == local or
            f"{first}{last[0]}" == local or
            f"{first[0]}.{last}" == local or
            f"{last}.{first}" == local or
            f"{last}{first}" == local or
            f"{last}_{first}" == local or
            last == local or
            f"{first[0]}_{last}" == local or
            f"{first[0]}{last[0]}" == local)


def role_matches_email(title: str, email_local: str) -> bool:
    """Check if office title suggests this email is for the role."""
    title_lower = title.lower()
    for role_key, local_hints in ROLE_MAP.items():
        if role_key in title_lower:
            if email_local in local_hints:
                return True
    return False


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT id, jurisdiction_type, jurisdiction_name, person_name,
               office_title, phone, email, source_url, contact_type
        FROM contacts
        ORDER BY jurisdiction_name, id
    """)
    contacts = [dict(r) for r in rows]
    await conn.close()

    # Load scraped emails from CSV
    scraped_path = OUT_DIR / "scraped_findings.csv"
    jur_emails: dict[str, set[str]] = defaultdict(set)

    if scraped_path.exists():
        with open(scraped_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                jur = r["jurisdiction_name"]
                for e in r["found_emails"].split("; "):
                    if e.strip():
                        jur_emails[jur].add(e.strip())
                if r.get("matched_email"):
                    jur_emails[jur].add(r["matched_email"])

    # Also collect domain knowledge from existing contacts
    jur_domains: dict[str, Counter] = defaultdict(Counter)
    for c in contacts:
        if c["email"]:
            domain = c["email"].split("@")[-1].lower()
            if domain not in PERSONAL_DOMAINS:
                jur_domains[c["jurisdiction_name"]][domain] += 1

    # Build assignment plan
    results = []
    by_jur = defaultdict(list)
    for c in contacts:
        by_jur[c["jurisdiction_name"]].append(c)

    strategy_counts = Counter()

    for jur_name, jur_contacts in sorted(by_jur.items()):
        emails_pool = jur_emails.get(jur_name, set())
        # Filter to official-domain emails (not personal, not false-positive scraper domains)
        official_emails = set()
        generic_emails = set()
        for e in emails_pool:
            domain = e.split("@")[-1].lower()
            if domain in PERSONAL_DOMAINS or domain in SCRAPER_FALSE_POSITIVES:
                continue
            local = e.split("@")[0].lower()
            if local in GENERIC_LOCALS:
                generic_emails.add(e)
            else:
                official_emails.add(e)

        # Also check if we know this jurisdiction's official domain
        official_domain = None
        if jur_domains.get(jur_name):
            official_domain = jur_domains[jur_name].most_common(1)[0][0]

        for c in jur_contacts:
            if c["email"]:
                continue  # Already has email

            assigned_email = ""
            strategy = ""

            # Strategy 1: Name match against scraped emails
            if c["person_name"] and official_emails:
                for e in official_emails:
                    if name_matches_email(c["person_name"], e):
                        assigned_email = e
                        strategy = "name_match"
                        break

            # Strategy 2: Role match
            if not assigned_email and c["office_title"] and official_emails:
                for e in official_emails:
                    local = e.split("@")[0].lower()
                    if role_matches_email(c["office_title"], local):
                        assigned_email = e
                        strategy = "role_match"
                        break

            # Strategy 3: If jurisdiction has generic contact email and this
            # contact is a primary role (clerk/mayor/manager), assign it
            if not assigned_email and generic_emails and c["office_title"]:
                title_lower = c["office_title"].lower()
                primary_roles = ["clerk", "mayor", "manager", "administrator",
                                "treasurer", "secretary"]
                if any(r in title_lower for r in primary_roles):
                    # Assign the first generic email
                    assigned_email = sorted(generic_emails)[0]
                    strategy = "generic_primary_role"

            # Strategy 4: If this jurisdiction only has ONE official email
            # found and this is the clerk/secretary, assign it — but only if
            # the email doesn't clearly belong to a different role
            if not assigned_email and len(official_emails) == 1 and c["office_title"]:
                title_lower = c["office_title"].lower()
                sole_email = list(official_emails)[0]
                sole_local = sole_email.split("@")[0].lower()
                # Don't assign mayor@ to a clerk, or clerk@ to a mayor, etc.
                role_conflicts = {
                    "clerk": ["mayor", "police", "fire", "judge", "attorney", "permits", "fairground", "election"],
                    "mayor": ["clerk", "police", "fire", "judge", "attorney", "permits", "fairground"],
                    "treasurer": ["mayor", "police", "fire", "judge", "attorney", "fairground"],
                }
                dominated_role = None
                for role_kw in role_conflicts:
                    if role_kw in title_lower:
                        dominated_role = role_kw
                        break
                conflicted = False
                if dominated_role:
                    for conflict in role_conflicts[dominated_role]:
                        if conflict in sole_local:
                            conflicted = True
                            break
                if not conflicted and ("clerk" in title_lower or "secretary" in title_lower):
                    # Extra check: if the email looks like a person's name (e.g. leea@)
                    # and this contact has a DIFFERENT name, skip
                    if c["person_name"] and sole_local.isalpha() and len(sole_local) > 3:
                        cleaned = clean_name(c["person_name"])
                        if cleaned:
                            first, last = cleaned
                            if first[0] != sole_local[0] and last[0] != sole_local[0]:
                                conflicted = True
                    if not conflicted:
                        assigned_email = sole_email
                        strategy = "sole_official_to_clerk"

            if assigned_email:
                strategy_counts[strategy] += 1
                results.append({
                    "contact_id": c["id"],
                    "jurisdiction_name": jur_name,
                    "person_name": c["person_name"] or "",
                    "office_title": c["office_title"] or "",
                    "new_email": assigned_email,
                    "match_type": strategy,
                    "confidence": "high" if strategy == "name_match" else "medium",
                })

    # Write output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outpath = OUT_DIR / "aggressive_email_apply.csv"
    if results:
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contact_id", "jurisdiction_name", "person_name", "office_title",
                "new_email", "match_type", "confidence",
            ])
            writer.writeheader()
            writer.writerows(results)

    print(f"Aggressive enrichment analysis:")
    print(f"  Contacts still missing email: {sum(1 for c in contacts if not c['email'])}")
    print(f"  New assignments found: {len(results)}")
    print(f"  By strategy:")
    for strat, count in strategy_counts.most_common():
        print(f"    {strat}: {count}")
    print(f"  Output: {outpath}")

    # Show unique counts
    unique_ids = {r["contact_id"] for r in results}
    print(f"  Unique contacts: {len(unique_ids)}")


if __name__ == "__main__":
    asyncio.run(main())
