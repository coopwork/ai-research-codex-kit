#!/usr/bin/env python3
"""Instantiate empty templates for a new research run (never fabricates sources)."""
import argparse
import re
import shutil
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    args = p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", args.slug):
        p.error("slug: lowercase a-z, digits, hyphens only; max 61 chars")
    root = Path(__file__).resolve().parents[1]
    dest = root / "runs" / args.slug
    if dest.exists():
        p.error(f"refusing to overwrite existing run: {dest}")
    dest.mkdir(parents=True)
    for src in (root / "templates").iterdir():
        if src.is_file():
            shutil.copyfile(src, dest / src.name)
    print(dest)


if __name__ == "__main__":
    main()
