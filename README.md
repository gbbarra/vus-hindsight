# vus-hindsight

A public benchmark measuring how often ClinVar variants of uncertain
significance (VUS) were later reclassified to a definitive call — and sizing the
pathogenic arm specifically, so it can be used to evaluate variant
interpretation methods.

> **Status:** the analysis code is complete and validated against a synthetic
> fixture, but **no real counts have been produced yet** — this sandbox's egress
> policy blocks `ftp.ncbi.nlm.nih.gov`. See
> [`results/STATUS.md`](results/STATUS.md). No estimated or placeholder numbers
> appear anywhere in this repository.

## What this measures

Take a ClinVar snapshot from the past. Select every variant classified
*Uncertain significance* at that date. Follow those same variants (by
`VariationID`) into the current ClinVar release and ask what became of them:

| outcome | meaning |
|---|---|
| **P/LP** | now Pathogenic or Likely pathogenic |
| **B/LB** | now Benign or Likely benign |
| **Still VUS** | unchanged |
| **Conflicting** | now has conflicting classifications |
| **Other** | drug response, risk factor, protective, not provided, … |
| **Retired/absent** | `VariationID` no longer in the current release |

Two baselines are used — mid-2021 and end-2022 — giving a longer and a shorter
follow-up window, so the reclassification rate can be read against elapsed time
rather than as a single opaque number.

The headline output is the **VUS → P/LP** arm, broken down by molecular
consequence and by review status, with distinct gene counts. The stratum of
greatest interest is **missense variants that reached at least
`criteria provided, multiple submitters`** — missense because it is where
computational prediction is weakest and truncating shortcuts do not apply, and
≥2 stars because multi-submitter agreement makes the current label a much
sturdier target.

## Why retrospective reclassification works as ground truth

A variant that was uncertain in 2021 and is confidently pathogenic today is a
case where the answer was knowable in principle but not yet established in
practice. That gives a benchmark three properties that are hard to obtain
otherwise:

1. **The label is independent of the input.** The evidence that resolved the
   variant — segregation, functional assays, case counts — arrived *after* the
   baseline snapshot. A method given only the baseline-era view is being asked
   to anticipate a conclusion, not to recall one.
2. **The labels come from expert human adjudication under a published rubric**
   (ACMG/AMP), submitted by clinical laboratories, not from a proxy signal like
   allele frequency or a computational score. Restricting to review statuses
   with assertion criteria keeps unreviewed single-submitter noise out.
3. **It is exactly the operational task.** Labs care about which of today's VUS
   will turn out to be actionable. This measures performance on that task
   directly, on the variants that actually made the transition.

**Caveats a reviewer should know.** Reclassification is not a random sample of
truth: variants in well-studied genes and in patients who got tested resolve
faster, so the reclassified set is enriched for clinically salient genes. The
current label is the best available consensus, not certainty — some will move
again. And because ClinVar aggregates submitters, a "new" classification can
reflect a single well-resourced lab rather than independent replication; the
review-status stratification in the output is there so this can be controlled
for rather than ignored.

**Frozen-evidence caveat.** Selecting the cohort from a past snapshot is not the
same as reconstructing what a lab could have known at that date. Any prediction
method evaluated here must not use post-baseline evidence.
`scripts/05_submission_summary_probe.sh` checks whether ClinVar's
`submission_summary` carries per-submission dates that would support a properly
frozen reconstruction.

## Method

- Source: ClinVar `variant_summary.txt.gz` (current) and two archived snapshots
  from `tab_delimited/archive/`. Filenames are **resolved from the live
  directory listing at runtime**, never hardcoded.
- Restricted to `Assembly = 'GRCh38'`; deduplicated on `VariationID`.
- Baseline VUS cohort **excludes** review status
  *no assertion criteria provided* (0-star).
- All I/O streams through DuckDB `read_csv` — snapshots are never loaded into
  pandas or held in memory. Raw snapshots are deleted immediately after
  processing, so peak disk stays near one baseline plus the current release.

### Column naming

ClinVar renamed its classification columns around 2024. Older snapshots use
`ClinicalSignificance` / `ReviewStatus`; current ones use
`GermlineClassification` / `GermlineReviewStatus`. `scripts/schema.py` resolves
these from the actual header of each file and raises if a required column is
absent — it never assumes a layout.

### Molecular consequence is derived, not read

`variant_summary` carries **no molecular-consequence column**. Consequence is
therefore derived from the HGVS expression in the `Name` field, in this
precedence order:

| class | matched on |
|---|---|
| frameshift | `p.Xxx###fs` |
| nonsense | `p.Xxx###Ter` / `p.Xxx###*` |
| splice | `c.###+N` / `c.###-N` (intronic offset) |
| missense | `p.Xxx###Yyy`, excluding synonymous `p.Xxx###=` |
| other | everything else |

Truncating classes are matched before missense so a frameshift is never counted
as a substitution. If a future snapshot adds a real consequence column,
`schema.py` prefers it automatically and the report records which source was
used. This derivation is the one methodological substitution in the pipeline and
is called out here because reviewers should be able to check it.

## Reproduce

```bash
pip install duckdb
scripts/run_all.sh                                # baselines 2021-06 and 2022-12
BASELINES="2021-06 2022-12" scripts/run_all.sh    # or choose your own
```

Requires outbound access to `ftp.ncbi.nlm.nih.gov`. Roughly 10 GB of free disk
is comfortable; the script prints free disk before starting and after each
baseline.

Validate the analysis logic without downloading anything:

```bash
python3 tests/test_pipeline.py
```

This runs the pipeline over a synthetic fixture with known expected counts,
checking column adaptation in both naming eras, the GRCh38 filter, `VariationID`
deduplication, classification bucketing, the review-status star ladder, and
consequence derivation.

## Layout

```
scripts/01_list_clinvar_ftp.sh         list FTP dir + archive/ (authoritative names)
scripts/02_fetch_snapshot.sh           fetch one snapshot by resolved exact name
scripts/03_headers.py                  print real header before any query runs
scripts/schema.py                      column resolution, buckets, stars, consequence
scripts/04_transitions.py              the analysis (DuckDB streaming)
scripts/05_submission_summary_probe.sh size-check + date-column probe
scripts/06_report.py                   assemble results/transitions.md
scripts/run_all.sh                     end-to-end, one baseline at a time
tests/                                 synthetic fixture + assertions
results/                               committed outputs
```

## Outputs

- `results/transitions.md` — every count and table
- `results/reclassified_pathogenic.tsv` — per-variant VUS → P/LP records
  (`VariationID`, gene, HGVS, consequence, baseline class, current class, review
  status), gzipped if over 50 MB
- `results/_counts_<baseline>.json` — machine-readable counts

## Review-status star ladder

| stars | ClinVar review status |
|---|---|
| 0 | no assertion criteria provided *(excluded from cohorts)* |
| 1 | criteria provided, single submitter · criteria provided, conflicting |
| 2 | criteria provided, multiple submitters, no conflicts |
| 3 | reviewed by expert panel |
| 4 | practice guideline |

## License

See [LICENSE](LICENSE).
