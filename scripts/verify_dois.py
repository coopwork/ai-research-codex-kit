#!/usr/bin/env python3
"""Cross-check DOI titles and years against Crossref metadata without editing sources.

Crossref 404 is NOT evidence of a fake DOI (some belong to other agencies).
This script cannot verify experimental claims or article retraction status.
"""
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


def normalized(s):
    t = unicodedata.normalize("NFKC", s or "").lower()
    return " ".join(re.findall(r"\w+", t, re.UNICODE))


def compare(source, item):
    known_title = source.get("title", "")
    actual_title = (item.get("title") or [""])[0]
    title_similarity = round(SequenceMatcher(None, normalized(known_title), normalized(actual_title)).ratio(), 3)
    published = item.get("published") or item.get("issued") or {}
    dates = published.get("date-parts") or []
    actual_year = dates[0][0] if dates and dates[0] else None
    year_match = source.get("year") == actual_year
    return {
        "registered_doi": item.get("DOI"),
        "registered_title": actual_title,
        "registered_year": actual_year,
        "title_similarity": title_similarity,
        "title_match_likely": title_similarity >= 0.87,
        "year_match": year_match,
        "authors_in_crossref": [" ".join((a.get("given", ""), a.get("family", ""))).strip() for a in item.get("author", [])],
        "note": "Title/year comparison only. Verify authors, corrections, retractions and findings separately."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()
    src_file = args.run / "sources.json"
    try:
        sources = json.loads(src_file.read_text(encoding="utf-8")).get("sources", [])
    except (OSError, ValueError) as e:
        print(f"Cannot read sources.json: {e}", file=sys.stderr)
        return 2
    checks = []
    for source in sources:
        sid = source.get("id", "UNKNOWN")
        doi = (source.get("doi") or "").replace("https://doi.org/", "").strip()
        record = {"id": sid, "doi": doi}
        if not doi:
            record["status"] = "NO_DOI_CHECK_PUBLISHER_MANUALLY"
            checks.append(record)
            continue
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIStudyKitResearch/1.0 (DOI metadata audit)"})
            with urllib.request.urlopen(req, timeout=20) as response:
                item = json.load(response)["message"]
            record["status"] = "FOUND_IN_CROSSREF"
            record.update(compare(source, item))
            if not record["title_match_likely"] or not record["year_match"]:
                record["status"] = "METADATA_DISCREPANCY_REVIEW_REQUIRED"
        except urllib.error.HTTPError as e:
            record["status"] = "NOT_VERIFIED_BY_CROSSREF"
            record["detail"] = f"HTTP {e.code}; may be another DOI agency, or an unavailable/incorrect DOI"
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            record["status"] = "NETWORK_OR_PARSE_ERROR"
            record["detail"] = str(e)
        checks.append(record)
        if args.sleep > 0:
            time.sleep(args.sleep)
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "limits": "Does not establish article content accuracy or retraction status."}
    dest = args.run / "doi_audit.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {dest}. Review mismatches and non-Crossref DOIs manually.")
    return 1 if any(x["status"] == "METADATA_DISCREPANCY_REVIEW_REQUIRED" for x in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
