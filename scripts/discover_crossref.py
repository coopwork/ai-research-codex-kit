#!/usr/bin/env python3
"""Find Crossref metadata candidates via its public REST API.

These are *candidates*, not verified sources or scientific evidence.
No automated requests to Google Scholar are performed.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AIStudyKitResearch/1.0 (research-metadata; respect limits)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def simple_item(item):
    date_parts = (item.get("published") or item.get("issued") or {}).get("date-parts", [[None]])
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    authors = [" ".join(x for x in (a.get("given", ""), a.get("family", "")) if x) for a in item.get("author", [])]
    return {
        "title": (item.get("title") or [""])[0],
        "authors": authors,
        "year": year,
        "doi": item.get("DOI"),
        "url": item.get("URL"),
        "journal": (item.get("container-title") or [""])[0],
        "publisher": item.get("publisher"),
        "type": item.get("type"),
        "metadata_source": "Crossref API",
        "status": "candidate_unverified",
        "access_level": "metadata_only",
    }


def main():
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Search publication metadata by keyword/title")
    group.add_argument("--doi", help="Retrieve metadata for an exact DOI")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if not 1 <= args.limit <= 25:
        p.error("--limit must be 1..25")
    mailto = os.environ.get("CROSSREF_MAILTO", "")
    qs = {"rows": args.limit, "query.bibliographic": args.query or ""}
    if mailto:
        qs["mailto"] = mailto
    url = ("https://api.crossref.org/works/" + urllib.parse.quote(args.doi.strip(), safe="/")) if args.doi else (
        "https://api.crossref.org/works?" + urllib.parse.urlencode(qs))
    try:
        payload = request_json(url)
        message = payload.get("message", {})
        items = message if args.doi else message.get("items", [])
        if isinstance(items, dict):
            items = [items]
        result = {"request_url": url, "source": "Crossref", "records": [simple_item(x) for x in items],
                  "verification_warning": "Records are NOT verified and are not evidence of study findings."}
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"Saved {len(items)} metadata candidates to {args.out}")
        else:
            print(text)
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f"Crossref unavailable: {err}. Mark as BLOCKED; never fabricate results.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
