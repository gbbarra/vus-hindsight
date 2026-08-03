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
        "REVIEW", "NumberSubmitters", "VariationID",
        "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF"]

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
        "PositionVCF": str(900000 + vid), "ReferenceAlleleVCF": "C",
        "AlternateAlleleVCF": "T",
    }
    return "\t".join(d[c] for c in COLS)


# Synthetic VCF MC terms, keyed by VariationID. Two deliberate design choices:
#   * VID 2 is nonsense by HGVS but frameshift by MC — proves the VCF wins.
#   * VID 10 is absent entirely — proves 'not_in_vcf' is reported, not folded
#     into 'other'.
#   * VID 1 carries two terms — proves missense outranks intron_variant.
VCF_MC = {
    1:  "SO:0001627|intron_variant,SO:0001583|missense_variant",
    2:  "SO:0001589|frameshift_variant",
    3:  "SO:0001819|synonymous_variant",
    4:  "SO:0001627|intron_variant",
    11: "SO:0001589|frameshift_variant",
    12: "SO:0001575|splice_donor_variant",
    13: "SO:0001583|missense_variant",
}

VCF_HEADER = [
    "##fileformat=VCFv4.1",
    '##INFO=<ID=ALLELEID,Number=1,Type=Integer,Description="ClinVar Allele ID">',
    '##INFO=<ID=GENEINFO,Number=1,Type=String,Description="Gene(s)">',
    '##INFO=<ID=MC,Number=.,Type=String,Description="comma separated list of '
    'molecular consequence in the form of Sequence Ontology ID|molecular_consequence">',
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
]


def write_vcf(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gene_by_vid = {vid: gene for vid, gene, *_ in CASES}
    with gzip.open(path, "wt") as fh:
        for line in VCF_HEADER:
            fh.write(line + "\n")
        for vid, mc in sorted(VCF_MC.items()):
            info = (f"ALLELEID={vid * 10};GENEINFO={gene_by_vid[vid]}:{vid};MC={mc}")
            fh.write(f"17\t{43000000 + vid}\t{vid}\tG\tA\t.\t.\t{info}\n")
    print(f"wrote {path} ({len(VCF_MC)} records)")


# --- submission_summary fixture, for the frozen-date reconstruction ----------
# One row per SCV. Each case pins down one rule of ClinVar's aggregation, so a
# regression in aggregate.py fails here instead of in a 366 MB download.
SUB_COLS = ["VariationID", "ClinicalSignificance", "DateLastEvaluated",
            "Description", "SubmittedPhenotypeInfo", "ReportedPhenotypeInfo",
            "ReviewStatus", "CollectionMethod", "OriginCounts", "Submitter",
            "SCV", "SubmittedGeneSymbol", "ExplanationOfInterpretation",
            "SomaticClinicalImpact", "Oncogenicity",
            "ContributesToAggregateClassification"]

CRIT = "criteria provided, single submitter"
NOCRIT_SUB = "no assertion criteria provided"
EXPERT_SUB = "reviewed by expert panel"
GUIDE_SUB = "practice guideline"

# (vid, class, date, review, submitter, contributes)
SUBMISSIONS = [
    # 100: two submitters agreeing -> 2 stars, Pathogenic
    (100, "Pathogenic", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (100, "Pathogenic", "Feb 10, 2020", CRIT, "Lab B", "yes"),
    # 101: P vs VUS across submitters -> conflict, 1 star
    (101, "Pathogenic", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (101, "Uncertain significance", "Feb 10, 2020", CRIT, "Lab B", "yes"),
    # 102: single submitter VUS -> 1 star
    (102, "Uncertain significance", "Mar 01, 2020", CRIT, "Lab A", "yes"),
    # 103: expert panel overrides a disagreeing ordinary submission -> 3 stars
    (103, "Uncertain significance", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (103, "Pathogenic", "Feb 01, 2020", EXPERT_SUB, "Panel X", "yes"),
    # 104: only submissions without criteria -> 0 stars
    (104, "Pathogenic", "Jan 05, 2020", NOCRIT_SUB, "Lab C", "yes"),
    # 105: Pathogenic + Likely pathogenic is NOT a conflict -> P/LP, 2 stars
    (105, "Pathogenic", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (105, "Likely pathogenic", "Feb 10, 2020", CRIT, "Lab B", "yes"),
    # 106: evaluated AFTER the cutoff -> variant absent from the reconstruction
    (106, "Pathogenic", "Jan 05, 2024", CRIT, "Lab A", "yes"),
    # 107: flagged as not contributing -> ignored
    (107, "Pathogenic", "Jan 05, 2020", CRIT, "Lab A", "no"),
    # 108: Benign + Likely benign -> B/LB, 2 stars
    (108, "Benign", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (108, "Likely benign", "Feb 10, 2020", CRIT, "Lab B", "yes"),
    # 109: same submitter twice is still ONE submitter -> 1 star, not 2
    (109, "Pathogenic", "Jan 05, 2020", CRIT, "Lab A", "yes"),
    (109, "Pathogenic", "Feb 10, 2020", CRIT, "Lab A", "yes"),
    # 110: practice guideline outranks an expert panel -> 4 stars
    (110, "Pathogenic", "Jan 05, 2020", EXPERT_SUB, "Panel X", "yes"),
    (110, "Likely pathogenic", "Feb 01, 2020", GUIDE_SUB, "Guideline Y", "yes"),
    # 111: missing date -> excluded, so this variant never appears
    (111, "Pathogenic", "-", CRIT, "Lab A", "yes"),
]


def write_submissions(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write("##Overview of interpretation, phenotypes and methods\n")
        fh.write("##Explanation of the columns in this report\n")
        fh.write("#" + "\t".join(SUB_COLS) + "\n")
        for vid, cls, date, review, submitter, contributes in SUBMISSIONS:
            row = {c: "-" for c in SUB_COLS}
            row.update({"VariationID": str(vid), "ClinicalSignificance": cls,
                        "DateLastEvaluated": date, "ReviewStatus": review,
                        "Submitter": submitter,
                        "SCV": f"SCV{vid}{submitter[-1]}{date[:3]}",
                        "ContributesToAggregateClassification": contributes})
            fh.write("\t".join(row[c] for c in SUB_COLS) + "\n")
    print(f"wrote {path} ({len(SUBMISSIONS)} submissions)")


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
    write_vcf(os.path.join(OUT, "clinvar_fixture.vcf.gz"))
    write_submissions(os.path.join(OUT, "submission_fixture.txt.gz"))


if __name__ == "__main__":
    main()
