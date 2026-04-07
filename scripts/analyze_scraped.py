#!/usr/bin/env python3
"""
Analyze scraped findings and produce an apply-ready CSV.

For each contact missing an email, tries to assign the best email:
1. Name-matched email (highest confidence)
2. If jurisdiction has a dominant official domain, infer from pattern
3. If contact is a generic role (City Clerk, etc.), match generic emails

For phones: apply found phones to contacts missing them.
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "data" / "enrichment"

PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "att.net", "sbcglobal.net", "cox.net",
    "icloud.com", "me.com", "live.com", "msn.com",
    "pldi.net", "suddenlink.net", "windstream.net",
    "valornet.com", "pistbb.com", "cableone.net",
    "fullspectrum.net", "rocketmail.com", "ymail.com",
}

# Generic role keywords -> email local parts that might match
ROLE_EMAIL_HINTS = {
    "clerk": ["clerk", "cityclerk", "townclerk", "city.clerk", "town.clerk"],
    "mayor": ["mayor"],
    "treasurer": ["treasurer", "finance"],
    "manager": ["citymanager", "city.manager", "manager", "townmanager"],
    "administrator": ["admin", "administrator", "cityadmin"],
    "chief": ["chief", "police.chief", "fire.chief", "firechief", "policechief"],
    "police": ["police", "pd", "policechief", "police.chief"],
    "fire": ["fire", "firechief", "fire.chief", "firedept"],
    "attorney": ["attorney", "cityattorney", "city.attorney"],
    "judge": ["judge", "court"],
}

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def clean_name(name: str) -> tuple[str, str] | None:
    parts = name.lower().split()
    while len(parts) > 1 and parts[-1] in NAME_SUFFIXES:
        parts.pop()
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


def match_email_to_contact(emails: list[str], person_name: str | None,
                           office_title: str | None) -> str | None:
    """Try to match one of the found emails to this contact."""
    if not emails:
        return None

    # Filter to official-domain emails only
    official_emails = [e for e in emails if e.split("@")[-1] not in PERSONAL_DOMAINS]
    if not official_emails:
        official_emails = emails  # fall back to all

    # Strategy 1: Name match
    if person_name:
        cleaned = clean_name(person_name)
        if cleaned:
            first, last = cleaned
            for e in official_emails:
                local = e.split("@")[0].lower()
                if (f"{first}.{last}" == local or
                    f"{first}{last}" == local or
                    f"{first}_{last}" == local or
                    f"{first[0]}{last}" == local or
                    f"{first}{last[0]}" == local or
                    f"{first[0]}.{last}" == local or
                    f"{last}.{first}" == local or
                    f"{last}{first}" == local or
                    last == local):
                    return e

    # Strategy 2: Role match
    if office_title:
        title_lower = office_title.lower()
        for role_keyword, email_hints in ROLE_EMAIL_HINTS.items():
            if role_keyword in title_lower:
                for e in official_emails:
                    local = e.split("@")[0].lower()
                    if local in email_hints:
                        return e

    return None


def main():
    scraped_path = OUT_DIR / "scraped_findings.csv"
    if not scraped_path.exists():
        print("No scraped_findings.csv found. Run 'scrape' first.")
        return

    with open(scraped_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Group scraped data by jurisdiction to build email pools
    jur_emails: dict[str, set[str]] = defaultdict(set)
    jur_phones: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        jur = r["jurisdiction_name"]
        for e in r["found_emails"].split("; "):
            if e.strip():
                jur_emails[jur].add(e.strip())
        if r.get("matched_email"):
            jur_emails[jur].add(r["matched_email"])
        for p in r["found_phones"].split("; "):
            if p.strip():
                jur_phones[jur].add(p.strip())

    # Build apply-ready output
    apply_rows = []
    matched_name = 0
    matched_role = 0
    phone_fills = 0

    for r in rows:
        if r["existing_email"]:
            # Already has email, skip email enrichment but check phone
            if not r["existing_phone"] and r["found_phones"]:
                first_phone = r["found_phones"].split("; ")[0]
                apply_rows.append({
                    "contact_id": r["contact_id"],
                    "jurisdiction_name": r["jurisdiction_name"],
                    "person_name": r["person_name"],
                    "office_title": r["office_title"],
                    "new_email": "",
                    "new_phone": first_phone,
                    "match_type": "phone_only",
                    "confidence": "medium",
                })
                phone_fills += 1
            continue

        # Contact is missing email - try to find the best match
        jur = r["jurisdiction_name"]
        all_jur_emails = list(jur_emails.get(jur, set()))

        # First: check the pre-computed matched_email
        email = r.get("matched_email", "").strip()
        match_type = "name_match"

        # If no pre-match, try our enhanced matching
        if not email:
            email = match_email_to_contact(
                all_jur_emails,
                r["person_name"],
                r["office_title"],
            ) or ""
            if email:
                # Determine match type based on how we matched
                cleaned = clean_name(r["person_name"]) if r["person_name"] else None
                if cleaned:
                    first, last = cleaned
                    local = email.split("@")[0].lower()
                    if (f"{first}.{last}" == local or f"{first}{last}" == local or
                        f"{first}_{last}" == local or f"{first[0]}{last}" == local or
                        f"{first}{last[0]}" == local or f"{first[0]}.{last}" == local or
                        f"{last}.{first}" == local or last == local):
                        match_type = "name_match"
                    else:
                        match_type = "role_match"
                else:
                    match_type = "role_match"

        if email:
            if match_type == "name_match":
                matched_name += 1
            else:
                matched_role += 1

        # Phone fill
        phone = ""
        if not r["existing_phone"] and r["found_phones"]:
            phone = r["found_phones"].split("; ")[0]
            phone_fills += 1

        if email or phone:
            apply_rows.append({
                "contact_id": r["contact_id"],
                "jurisdiction_name": r["jurisdiction_name"],
                "person_name": r["person_name"],
                "office_title": r["office_title"],
                "new_email": email,
                "new_phone": phone,
                "match_type": match_type if email else "phone_only",
                "confidence": "high" if match_type == "name_match" else "medium",
            })

    # Write apply-ready CSV
    outpath = OUT_DIR / "scrape_apply_ready.csv"
    if apply_rows:
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contact_id", "jurisdiction_name", "person_name", "office_title",
                "new_email", "new_phone", "match_type", "confidence",
            ])
            writer.writeheader()
            writer.writerows(apply_rows)

    print(f"Analysis complete:")
    print(f"  Total scraped rows: {len(rows)}")
    print(f"  Apply-ready rows: {len(apply_rows)}")
    print(f"  Name-matched emails: {matched_name}")
    print(f"  Role-matched emails: {matched_role}")
    print(f"  Phone fills: {phone_fills}")
    print(f"  Output: {outpath}")

    # Also show unique contacts that will get emails
    unique_email_contacts = set()
    for r in apply_rows:
        if r["new_email"]:
            unique_email_contacts.add(r["contact_id"])
    print(f"  Unique contacts getting new emails: {len(unique_email_contacts)}")

    unique_phone_contacts = set()
    for r in apply_rows:
        if r["new_phone"]:
            unique_phone_contacts.add(r["contact_id"])
    print(f"  Unique contacts getting new phones: {len(unique_phone_contacts)}")


if __name__ == "__main__":
    main()
