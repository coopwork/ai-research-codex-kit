#!/usr/bin/env python3
"""Find OpenAlex WORK metadata candidates; verify independently before citing."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 25:
        parser.error("--limit must be 1..25")
    params = {"search": args.query, "per_page": args.limit}
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params["api_key"] = key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AIStudyKitResearch/1.0 (metadata discovery)"})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.load(response)
        records = []
        for item in data.get("results", []):
            loc = item.get("best_oa_location") or item.get("primary_location") or {}
            records.append({
                "title": item.get("display_name", ""),
                "authors": [a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
                "year": item.get("publication_year"),
                "doi": item.get("doi"),
                "url": item.get("id"),
                "full_text_candidate": loc.get("pdf_url") or loc.get("landing_page_url"),
                "publication_type": item.get("type"),
                "citation_count": item.get("cited_by_count"),
                "metadata_source": "OpenAlex API",
                "status": "candidate_unverified",
                "access_level": "metadata_only",
            })
        out = {"source": "OpenAlex", "request_url": url.split("api_key=")[0] + ("<REDACTED>" if key else ""),
               "records": records,
               "verification_warning": "Candidate metadata only; article findings not checked."}
        result = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(result, encoding="utf-8")
            print(f"Saved {len(records)} candidates in {args.out}")
        else:
            print(result)
        return 0
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"OpenAlex unavailable: {e}; do not fabricate results.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
