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


# --- Molecular consequence ----------------------------------------------------
# variant_summary carries no consequence column, so we derive it from the HGVS
# in `Name`, e.g. "NM_000059.4(BRCA2):c.1234A>T (p.Lys412Ter)".
# Order matters: frameshift and nonsense are checked before missense so that a
# truncating change is never counted as a substitution.

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
