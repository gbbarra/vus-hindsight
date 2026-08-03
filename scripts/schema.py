"""Column resolution + classification logic shared by every analysis step.

Two things vary across ClinVar snapshots and are resolved from the real header:

  classification : "ClinicalSignificance"  (pre-2024 files)
                   "GermlineClassification" (current files)
  review_status  : "ReviewStatus"          (pre-2024 files)
                   "GermlineReviewStatus"  (current files)

Nothing here assumes a layout; if a required column is absent we raise rather
than silently substituting a default, because every number this repo emits is
meant to be verifiable.
"""

CLASSIFICATION_CANDIDATES = ("GermlineClassification", "ClinicalSignificance")
REVIEW_CANDIDATES = ("GermlineReviewStatus", "ReviewStatus")
# variant_summary has historically carried no molecular-consequence column.
# If a future snapshot adds one we prefer it; otherwise we derive consequence
# from HGVS (see CONSEQUENCE_SQL). Both paths are reported in the output.
CONSEQUENCE_CANDIDATES = ("MolecularConsequence", "MC", "Molecular consequence")

REQUIRED = ("VariationID", "GeneSymbol", "Name", "Assembly", "Type")


def _pick(columns, candidates):
    for cand in candidates:
        if cand in columns:
            return cand
    return None


def resolve_columns(columns):
    """Map logical names -> actual header names. Raises KeyError if missing."""
    cols = list(columns)
    resolved = {}

    classification = _pick(cols, CLASSIFICATION_CANDIDATES)
    if classification is None:
        raise KeyError(
            "no classification column found; looked for "
            f"{CLASSIFICATION_CANDIDATES}, header has {cols}"
        )
    resolved["classification"] = classification

    review = _pick(cols, REVIEW_CANDIDATES)
    if review is None:
        raise KeyError(
            f"no review-status column found; looked for {REVIEW_CANDIDATES}"
        )
    resolved["review_status"] = review

    for req in REQUIRED:
        if req not in cols:
            raise KeyError(f"required column {req!r} absent from header")
        resolved[req.lower()] = req

    # Optional; None means "derive from HGVS".
    resolved["consequence"] = _pick(cols, CONSEQUENCE_CANDIDATES)

    # Optional coordinate and date columns, needed only by the join export.
    # Absent in the synthetic fixtures, so callers must tolerate None.
    for key, candidates in (
            ("chromosome", ("Chromosome",)),
            ("position_vcf", ("PositionVCF",)),
            ("ref_vcf", ("ReferenceAlleleVCF",)),
            ("alt_vcf", ("AlternateAlleleVCF",)),
            ("last_evaluated", ("LastEvaluated",))):
        resolved[key] = _pick(cols, candidates)
    return resolved


# --- Classification bucketing -------------------------------------------------
# Buckets are matched on the lowercased, trimmed raw value. ClinVar reworded
# several values over time ("Conflicting interpretations of pathogenicity" ->
# "Conflicting classifications of pathogenicity"), so both spellings are matched.

def bucket_sql(col):
    """SQL CASE expression mapping a raw classification to a coarse bucket."""
    c = f"lower(trim({col}))"
    return f"""
    CASE
      WHEN {c} IN ('pathogenic','likely pathogenic',
                   'pathogenic/likely pathogenic',
                   'pathogenic/likely pathogenic; risk factor',
                   'pathogenic; risk factor','likely pathogenic; risk factor',
                   'pathogenic/likely pathogenic; other',
                   'pathogenic, low penetrance',
                   'likely pathogenic, low penetrance',
                   'pathogenic/likely pathogenic, low penetrance')
           THEN 'P/LP'
      WHEN {c} IN ('benign','likely benign','benign/likely benign',
                   'benign; risk factor','likely benign; risk factor',
                   'benign/likely benign; other')
           THEN 'B/LB'
      WHEN {c} LIKE 'conflicting%' THEN 'Conflicting'
      WHEN {c} IN ('uncertain significance','uncertain risk allele',
                   'uncertain significance/uncertain risk allele')
           THEN 'Still VUS'
      ELSE 'Other'
    END"""


# --- Review-status star ladder ------------------------------------------------
# 0 = no assertion criteria provided  (EXCLUDED from all baselines per protocol)
# 1 = criteria provided, single submitter / conflicting
# 2 = criteria provided, multiple submitters, no conflicts
# 3 = reviewed by expert panel
# 4 = practice guideline

def stars_sql(col):
    c = f"lower(trim({col}))"
    return f"""
    CASE
      WHEN {c} LIKE 'practice guideline%'            THEN 4
      WHEN {c} LIKE 'reviewed by expert panel%'      THEN 3
      WHEN {c} LIKE 'criteria provided, multiple submitters%' THEN 2
      WHEN {c} LIKE 'criteria provided, conflicting%' THEN 1
      WHEN {c} LIKE 'criteria provided, single submitter%'    THEN 1
      ELSE 0
    END"""


# --- Molecular consequence: primary source is the ClinVar VCF `MC` field ------
# The VCF INFO column carries MC=SO:0001583|missense_variant[,...], a stated
# Sequence Ontology term rather than something inferred from a name string.
# A variant may carry several terms (different transcripts), so we apply a fixed
# precedence: truncating classes win over missense, and missense wins over
# non-coding terms. Both the SO accession and the term name are matched, so a
# rename upstream cannot silently reroute variants into 'other'.

MC_PRECEDENCE = [
    ("frameshift", ["SO:0001589", "frameshift_variant"]),
    ("nonsense",   ["SO:0001587", "nonsense", "stop_gained"]),
    ("splice",     ["SO:0001574", "splice_acceptor_variant",
                    "SO:0001575", "splice_donor_variant"]),
    ("missense",   ["SO:0001583", "missense_variant"]),
]


def mc_bucket_sql(mc_col):
    """Map a raw MC string to one of frameshift/nonsense/splice/missense/other."""
    branches = []
    for label, needles in MC_PRECEDENCE:
        tests = " OR ".join(f"{mc_col} LIKE '%{n}%'" for n in needles)
        branches.append(f"WHEN {tests} THEN '{label}'")
    joined = "\n      ".join(branches)
    return f"""
    CASE
      WHEN {mc_col} IS NULL OR {mc_col} = '' THEN 'other'
      {joined}
      ELSE 'other'
    END"""


# --- Molecular consequence: secondary HGVS derivation (cross-check only) -------
# Retained so each VCF-assigned consequence can be compared against an
# independent derivation from the HGVS in `Name`, e.g.
# "NM_000059.4(BRCA2):c.1234A>T (p.Lys412Ter)". The concordance rate is reported
# in the output. This is a diagnostic; it is NOT the source of the published
# consequence breakdown.

def consequence_sql(name_col, type_col, explicit_col=None):
    if explicit_col:
        return f"lower(trim({explicit_col}))"
    n = name_col
    return f"""
    CASE
      WHEN regexp_matches({n}, 'p\\.[A-Za-z]{{3}}[0-9]+[A-Za-z]{{0,3}}fs') THEN 'frameshift'
      WHEN regexp_matches({n}, 'p\\.[A-Za-z]{{3}}[0-9]+(Ter|\\*)')         THEN 'nonsense'
      WHEN regexp_matches({n}, 'c\\.[0-9*+-]+[+-][0-9]+')                  THEN 'splice'
      WHEN regexp_matches({n}, 'p\\.[A-Za-z]{{3}}[0-9]+=')                 THEN 'other'
      WHEN regexp_matches({n}, 'p\\.[A-Za-z]{{3}}[0-9]+[A-Za-z]{{3}}')     THEN 'missense'
      WHEN lower({type_col}) LIKE '%deletion%'
        OR lower({type_col}) LIKE '%duplication%'
        OR lower({type_col}) LIKE '%insertion%'                            THEN 'other'
      ELSE 'other'
    END"""
