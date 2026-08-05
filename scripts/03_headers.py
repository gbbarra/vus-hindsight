#!/usr/bin/env python3
"""Print the header row of a gzipped ClinVar TSV without decompressing it fully.

ClinVar renamed classification columns around 2024 (ClinicalSignificance ->
GermlineClassification, ReviewStatus -> GermlineReviewStatus). Every analysis
step resolves column names from the ACTUAL header via schema.py rather than
assuming a layout, so this script exists to make the real header visible in
the run log before any query executes.

Usage: 03_headers.py FILE.txt.gz [FILE2.txt.gz ...]
"""

import gzip
import sys

from schema import resolve_columns


def main(paths):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            header = fh.readline().rstrip("\n").lstrip("#")
        cols = header.split("\t")
        print(f"=== {path} ===")
        print(f"{len(cols)} columns")
        for i, c in enumerate(cols, 1):
            print(f"  {i:3d}  {c}")
        try:
            resolved = resolve_columns(cols)
        except KeyError as exc:
            print(f"  !! COLUMN RESOLUTION FAILED: {exc}")
            return 1
        print("  resolved ->")
        for k, v in resolved.items():
            print(f"      {k:16s} = {v}")
        print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
