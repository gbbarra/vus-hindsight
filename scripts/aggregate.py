"""Reconstructing ClinVar's aggregate germline classification from raw submissions.

`submission_summary.txt.gz` has one row per SCV (per submission). ClinVar
combines those into the single aggregate classification and review status that
`variant_summary` reports. To ask "what would ClinVar have said at date T" we
have to redo that combination using only submissions evaluated on or before T.

The rules below follow ClinVar's documented aggregation. They are stated here
rather than buried in SQL because they are the main source of error in this
analysis, and because 10_validate_reconstruction.py exists precisely to measure
how far the reconstruction lands from the real snapshot.

Review-status ladder (stars):

  4  practice guideline
  3  reviewed by expert panel
  2  criteria provided, multiple submitters, no conflicts
  1  criteria provided, single submitter
  1  criteria provided, conflicting classifications
  0  no assertion criteria provided

Aggregation:

  * A practice-guideline or expert-panel submission overrides everything; its
    classification becomes the aggregate.
  * Otherwise only submissions that provide assertion criteria are aggregated.
    Submissions without criteria contribute the 0-star fallback.
  * Conflict is declared across the medically distinct buckets P/LP, VUS and
    B/LB. Pathogenic vs Likely pathogenic is NOT a conflict — it aggregates to
    "Pathogenic/Likely pathogenic". Same for Benign vs Likely benign.
  * Two or more distinct submitters agreeing gives 2 stars; one gives 1.

KNOWN LIMITATION, and the reason validation is not optional: submission_summary
lists only submissions as they stand TODAY, each with its current
DateLastEvaluated. A laboratory that revised its SCV in 2023 appears with a 2023
date, so a reconstruction as of 2021 drops it — even though that laboratory did
have a submission in 2021, whose earlier content is no longer published
anywhere. Reconstruction therefore systematically UNDERCOUNTS the submissions
present at a past date, biasing toward fewer submitters and lower star ratings.
The validation quantifies that bias instead of assuming it away.
"""

# Which SCV-level classifications fall in which medically distinct bucket.
BUCKET_CASE = """
    CASE
      WHEN lower(trim(scv_class)) IN ('pathogenic','likely pathogenic',
                                      'pathogenic/likely pathogenic')
           THEN 'P/LP'
      WHEN lower(trim(scv_class)) IN ('benign','likely benign',
                                      'benign/likely benign')
           THEN 'B/LB'
      WHEN lower(trim(scv_class)) IN ('uncertain significance',
                                      'uncertain risk allele')
           THEN 'VUS'
      ELSE 'Other'
    END"""

# An SCV provides assertion criteria unless it says otherwise.
HAS_CRITERIA = "lower(trim(scv_review)) LIKE 'criteria provided%'"
IS_EXPERT = "lower(trim(scv_review)) LIKE 'reviewed by expert panel%'"
IS_GUIDELINE = "lower(trim(scv_review)) LIKE 'practice guideline%'"

# Dates appear as "Jun 03, 2021" in ClinVar's tab-delimited exports; the ISO
# form is accepted too so a format change does not silently drop every row.
DATE_PARSE = "try_strptime(date_last_evaluated, ['%b %d, %Y', '%Y-%m-%d'])"


def reconstruct_sql(as_of):
    """SQL producing one reconstructed row per VariationID as of `as_of`.

    Expects a table `subs` with columns variation_id, scv_class, scv_review,
    submitter, scv, date_last_evaluated, contributes.
    """
    return f"""
    WITH eligible AS (
        SELECT variation_id,
               scv_class,
               {BUCKET_CASE}      AS bucket,
               submitter,
               {HAS_CRITERIA}     AS has_criteria,
               {IS_EXPERT}        AS is_expert,
               {IS_GUIDELINE}     AS is_guideline
        FROM subs
        WHERE lower(trim(contributes)) = 'yes'
          AND {DATE_PARSE} IS NOT NULL
          AND {DATE_PARSE} <= DATE '{as_of}'
    ),
    per_variant AS (
        SELECT
            variation_id,
            count(*)                                              AS n_scv,
            count(*) FILTER (WHERE has_criteria)                  AS n_crit,
            count(DISTINCT submitter) FILTER (WHERE has_criteria) AS n_submitters,
            bool_or(is_expert)                                    AS any_expert,
            bool_or(is_guideline)                                 AS any_guideline,
            count(DISTINCT bucket) FILTER (
                WHERE has_criteria AND bucket IN ('P/LP','VUS','B/LB'))
                                                                  AS n_buckets,
            -- Buckets present among criteria-providing submissions.
            bool_or(has_criteria AND bucket = 'P/LP')             AS has_plp,
            bool_or(has_criteria AND bucket = 'B/LB')             AS has_blb,
            bool_or(has_criteria AND bucket = 'VUS')              AS has_vus,
            -- Exact classifications, to tell Pathogenic from Likely pathogenic.
            bool_or(has_criteria AND lower(trim(scv_class)) = 'pathogenic')       AS has_p,
            bool_or(has_criteria AND lower(trim(scv_class)) = 'likely pathogenic')AS has_lp,
            bool_or(has_criteria AND lower(trim(scv_class)) = 'benign')           AS has_b,
            bool_or(has_criteria AND lower(trim(scv_class)) = 'likely benign')    AS has_lb,
            -- A panel/guideline call, when one exists.
            max(CASE WHEN is_guideline THEN scv_class END)        AS guideline_class,
            max(CASE WHEN is_expert    THEN scv_class END)        AS expert_class
        FROM eligible GROUP BY variation_id
    )
    SELECT
        variation_id,
        n_scv, n_crit, n_submitters,
        CASE
          WHEN any_guideline THEN 4
          WHEN any_expert    THEN 3
          WHEN n_crit = 0    THEN 0
          WHEN n_buckets > 1 THEN 1          -- conflicting
          WHEN n_submitters >= 2 THEN 2
          ELSE 1
        END AS stars,
        CASE
          WHEN any_guideline THEN guideline_class
          WHEN any_expert    THEN expert_class
          WHEN n_crit = 0    THEN 'no assertion criteria provided'
          WHEN n_buckets > 1 THEN 'Conflicting classifications of pathogenicity'
          WHEN has_plp AND has_p AND has_lp THEN 'Pathogenic/Likely pathogenic'
          WHEN has_plp AND has_p            THEN 'Pathogenic'
          WHEN has_plp AND has_lp           THEN 'Likely pathogenic'
          WHEN has_plp                      THEN 'Pathogenic/Likely pathogenic'
          WHEN has_blb AND has_b AND has_lb THEN 'Benign/Likely benign'
          WHEN has_blb AND has_b            THEN 'Benign'
          WHEN has_blb AND has_lb           THEN 'Likely benign'
          WHEN has_blb                      THEN 'Benign/Likely benign'
          WHEN has_vus                      THEN 'Uncertain significance'
          ELSE 'Other'
        END AS classification,
        CASE
          WHEN any_guideline THEN 'practice guideline'
          WHEN any_expert    THEN 'reviewed by expert panel'
          WHEN n_crit = 0    THEN 'no assertion criteria provided'
          WHEN n_buckets > 1 THEN 'criteria provided, conflicting classifications'
          WHEN n_submitters >= 2
               THEN 'criteria provided, multiple submitters, no conflicts'
          ELSE 'criteria provided, single submitter'
        END AS review_status
    FROM per_variant
    """
