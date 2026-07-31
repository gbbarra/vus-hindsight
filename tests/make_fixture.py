#!/usr/bin/env python3
"""Build tiny SYNTHETIC ClinVar-shaped snapshots to test the analysis logic.

These are NOT ClinVar data and produce NO scientific results. They exist only to
prove that 04_transitions.py parses headers, adapts to the pre-2024 vs current
column naming, filters GRCh38, deduplicates on VariationID, buckets
classifications, maps the review-status star ladder, and derives molecular
consequence from HGVS.

The baseline fixture deliberately uses the OLD column names
(ClinicalSignificance / ReviewStatus) and the current fixture uses the NEW ones
(GermlineClassification / GermlineReviewStatus).
"""
import gzip
import os

OUT = os.path.join(os.path.dirname(__file__), "fixtures")

COLS = ["AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID",
        "CLASSIFICATION", "LastEvaluated", "Assembly", "Chromosome",
        "REVIEW", "NumberSubmitters", "VariationID"]

VUS = "Uncertain significance"
CRIT1 = "criteria provided, single submitter"
CRIT2 = "criteria provided, multiple submitters, no conflicts"
EXPERT = "reviewed by expert panel"
NOCRIT = "no assertion criteria provided"
CONFLICT = "criteria provided, conflicting classifications"

MISSENSE_1 = "NM_007294.4(BRCA1):c.299G>A (p.Arg100Gln)"
MISSENSE_10 = "NM_007294.4(BRCA1):c.5123C>A (p.Ala1708Glu)"
MISSENSE_13 = "NM_000251.3(MSH2):c.1786A>G (p.Asn596Asp)"
NONSENSE_2 = "NM_000059.4(BRCA2):c.598C>T (p.Gln200Ter)"
FRAMESHIFT_11 = "NM_000546.6(TP53):c.1234delA (p.Lys412fs)"
SPLICE_12 = "NM_000249.4(MLH1):c.1234+1G>A"
PLAIN = "NM_001.1(GENE):c.100A>G (p.Thr34Ala)"

# (VariationID, gene, name, assembly, baseline_class, baseline_review,
#  current_class, current_review)  -- current_* None => absent from current
CASES = [
    (1,  "BRCA1", MISSENSE_1,   "GRCh38", VUS, CRIT1, "Pathogenic", CRIT2),
    (2,  "BRCA2", NONSENSE_2,   "GRCh38", VUS, CRIT1, "Likely pathogenic", CRIT1),
    (3,  "ATM",   PLAIN,        "GRCh38", VUS, CRIT1, "Benign", CRIT2),
    (4,  "ATM",   PLAIN,        "GRCh38", VUS, CRIT1, VUS, CRIT1),
    (5,  "PALB2", PLAIN,        "GRCh38", VUS, CRIT1,
         "Conflicting classifications of pathogenicity", CONFLICT),
    (6,  "CFTR",  PLAIN,        "GRCh38", VUS, NOCRIT, "Pathogenic", CRIT2),
    (7,  "RET",   PLAIN,        "GRCh38", VUS, CRIT1, None, None),
    (8,  "BRCA1", PLAIN,        "GRCh38", "Pathogenic", CRIT2, "Pathogenic", CRIT2),
    (9,  "BRCA1", PLAIN,        "GRCh37", VUS, CRIT1, "Pathogenic", CRIT2),
    (10, "BRCA1", MISSENSE_10,  "GRCh38", VUS, CRIT1, "Pathogenic", CRIT2),
    (11, "TP53",  FRAMESHIFT_11,"GRCh38", VUS, CRIT1, "Likely pathogenic", CRIT2),
    (12, "MLH1",  SPLICE_12,    "GRCh38", VUS, CRIT1, "Pathogenic", CRIT2),
    (13, "MSH2",  MISSENSE_13,  "GRCh38", VUS, CRIT1, "Pathogenic", EXPERT),
    (14, "VKORC1",PLAIN,        "GRCh38", VUS, CRIT1, "drug response", CRIT1),
]


def row(vid, gene, name, assembly, cls, review):
    d = {
        "AlleleID": str(vid * 10), "Type": "single nucleotide variant",
        "Name": name, "GeneID": str(vid), "GeneSymbol": gene, "HGNC_ID": "-",
        "CLASSIFICATION": cls, "LastEvaluated": "Jan 01, 2020",
        "Assembly": assembly, "Chromosome": "17", "REVIEW": review,
        "NumberSubmitters": "3", "VariationID": str(vid),
    }
    return "\t".join(d[c] for c in COLS)


def write(path, header_cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write("#" + "\t".join(header_cols) + "\n")
        for r in rows:
            fh.write(r + "\n")
    print(f"wrote {path} ({len(rows)} rows)")


def main():
    base_cols = [("ClinicalSignificance" if c == "CLASSIFICATION" else
                  "ReviewStatus" if c == "REVIEW" else c) for c in COLS]
    cur_cols = [("GermlineClassification" if c == "CLASSIFICATION" else
                 "GermlineReviewStatus" if c == "REVIEW" else c) for c in COLS]

    base_rows, cur_rows = [], []
    for vid, gene, name, asm, bcls, brev, ccls, crev in CASES:
        base_rows.append(row(vid, gene, name, asm, bcls, brev))
        if vid == 10:  # duplicate VariationID in baseline -> dedupe must collapse
            base_rows.append(row(vid, gene, name, asm, bcls, brev))
        if ccls is not None:
            cur_rows.append(row(vid, gene, name, asm, ccls, crev))

    write(os.path.join(OUT, "baseline_fixture.txt.gz"), base_cols, base_rows)
    write(os.path.join(OUT, "current_fixture.txt.gz"), cur_cols, cur_rows)


if __name__ == "__main__":
    main()
