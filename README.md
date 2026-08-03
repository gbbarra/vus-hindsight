# vus-hindsight

A public benchmark measuring how often ClinVar variants of uncertain
significance (VUS) were later reclassified to a definitive call — and sizing the
pathogenic arm specifically, so it can be used to evaluate variant
interpretation methods.

> **Writing about this benchmark?** [`docs/BRIEFING.md`](docs/BRIEFING.md) is a
> self-contained handoff — every measured number, the exact release each came
> from, and the caveats that belong in any write-up.
>
> **Measured results:** [`results/transitions.md`](results/transitions.md),
> produced by `scripts/run_all.sh` on a GitHub Actions runner and committed
> straight from that run, with the full run log alongside them in
> `results/run_log.txt`. Provenance notes in
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

`submission_summary.txt.gz` does carry per-submission dates: it has one row per
SCV (per submission, not per variant) with a `DateLastEvaluated` column, plus
`Submitter`, `ReviewStatus` and the `SCV` accession. So a frozen reconstruction
is feasible in principle. Two limits matter, and
`scripts/05b_submission_dates.py` measures the first one directly rather than
assuming it:

- `DateLastEvaluated` is **not always populated** — it is `-` on some records.
  The measured coverage is reported in `results/_submission_dates.json`.
- It is the date the **submitter last evaluated** the record, not the date
  ClinVar published it. A record evaluated in 2019 may have reached ClinVar
  years later, so filtering on this date bounds what was *knowable* rather than
  replaying what was *public*. Treat a frozen-date cohort built this way as
  approximate, and say so in any write-up.

## Method

- Source: ClinVar `variant_summary.txt.gz` (current) and two archived snapshots,
  plus the GRCh38 `clinvar.vcf.gz` for molecular consequence. Filenames are
  **resolved from the live directory listing at runtime**, never hardcoded, and
  md5-verified against NCBI's published checksum where one exists.
- ClinVar keeps only about the last 18 months loose in `tab_delimited/archive/`
  and files older snapshots under `archive/<YEAR>/`. The fetch step looks in the
  flat listing first, then in the year subdirectory, and fails loudly listing
  what *is* available rather than guessing a path.
- Restricted to `Assembly = 'GRCh38'`; deduplicated on `VariationID`.
- Baseline VUS cohort **excludes** review status
  *no assertion criteria provided* (0-star).
- All I/O streams through DuckDB `read_csv` — snapshots are never loaded into
  pandas or held in memory. Raw snapshots are deleted immediately after
  processing, so peak disk stays near one baseline plus the current release.

### Column naming

`scripts/schema.py` resolves the classification and review columns from the
actual header of each file and raises if a required column is absent — it never
assumes a layout. It accepts both `ClinicalSignificance` / `ReviewStatus` and
`GermlineClassification` / `GermlineReviewStatus`.

Worth recording, because it is easy to get wrong from memory: as of the
2026-07 release, `variant_summary.txt.gz` **still uses
`ClinicalSignificance` and `ReviewStatus`**. ClinVar's germline/somatic split
did not rename those columns here — it added separate ones alongside them
(`SomaticClinicalImpact`, `ReviewStatusClinicalImpact`, `Oncogenicity`,
`ReviewStatusOncogenicity`, and the `SCVsForAggregate*` family), for 43 columns
total. `ClinicalSignificance` remains the aggregate **germline** classification,
which is what this benchmark measures; the somatic and oncogenicity columns are
deliberately untouched. The header of every snapshot is printed into the run log
before any query executes, so this can be checked rather than trusted.

### Molecular consequence comes from the ClinVar VCF

`variant_summary` carries no molecular-consequence column. Rather than infer
consequence from a name string, this benchmark reads it from the **`MC` field of
the ClinVar GRCh38 VCF** (`vcf_GRCh38/clinvar.vcf.gz`), which states a Sequence
Ontology term directly:

```
MC=SO:0001627|intron_variant,SO:0001583|missense_variant
```

The VCF's `ID` column is the `VariationID`, which joins straight back to
`variant_summary`. `scripts/03b_extract_mc.py` streams the VCF and writes a
compact `VariationID → consequence` map.

A variant may carry several `MC` terms (one per affected transcript), so a fixed
precedence applies — truncating classes outrank missense, missense outranks
non-coding terms:

| class | Sequence Ontology terms |
|---|---|
| frameshift | `SO:0001589` frameshift_variant |
| nonsense | `SO:0001587` nonsense / stop_gained |
| splice | `SO:0001574` splice_acceptor_variant, `SO:0001575` splice_donor_variant |
| missense | `SO:0001583` missense_variant |
| other | everything else (synonymous, intronic, UTR, …) |

Both the SO accession and the term name are matched, so an upstream rename
cannot silently reroute variants into `other`. Two reporting choices keep the
result auditable:

- Variants with **no VCF record** (typically those without a precise genomic
  placement) are reported as their own `not_in_vcf` row, never folded into
  `other`.
- `03b_extract_mc.py` prints the SO terms that landed in `other`, with counts, so
  nothing is miscategorised without being visible. It exits non-zero rather than
  degrading if the `MC` field is absent entirely.

The per-variant TSV carries the raw `MC` string alongside the assigned class, so
every single call can be checked against its source.

**Cross-check.** The older HGVS-based derivation is retained purely as an
independent second opinion: the report states what fraction of consequences
assigned from `MC` agree with it. That number is a diagnostic. Published
breakdowns use `MC` alone.

## Reproduce

### On GitHub Actions (no local setup)

`.github/workflows/benchmark.yml` runs the whole pipeline on a GitHub-hosted
runner and commits the results back to the branch. Actions → *ClinVar VUS
reclassification benchmark* → **Run workflow**, optionally overriding the
baseline months. It also re-runs automatically whenever anything under
`scripts/` changes. The full run log is committed as `results/run_log.txt`, and
the outputs are additionally attached to the run as an artifact.

The `workflow_dispatch` button only appears once this workflow file exists on
the repository's default branch — that is a GitHub requirement, not a project
one. Until then it still runs on push.

### Locally

```bash
pip install duckdb
scripts/run_all.sh                                # baselines 2021-06 and 2022-12
BASELINES="2021-06 2022-12" scripts/run_all.sh    # or choose your own
SUBMISSION_CONFIRM=1 scripts/run_all.sh           # allow the >2 GB submission_summary
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
scripts/03b_extract_mc.py              VariationID -> consequence from the VCF MC field
scripts/schema.py                      column resolution, buckets, stars, MC mapping
scripts/04_transitions.py              the analysis (DuckDB streaming)
scripts/05_submission_summary_probe.sh size-check + date-column probe
scripts/06_report.py                   assemble results/transitions.md
scripts/run_all.sh                     end-to-end, one baseline at a time
tests/                                 synthetic fixture + assertions
results/                               committed outputs
```

## Outputs

- `results/transitions.md` — every count and table
- `results/survival.md` — the fixed-cohort survival curve, with charts: one VUS
  cohort followed through several later snapshots, so elapsed time is the only
  thing varying
- `results/reclassified_pathogenic.tsv` — per-variant VUS → P/LP records
  (`VariationID`, gene, HGVS, consequence, raw `MC` string, baseline class,
  current class, review status), gzipped if over 50 MB
- `results/reclassified_benign.tsv` — the VUS → B/LB arm, identical schema.
  These are the negatives: a method's discrimination cannot be measured from the
  pathogenic arm alone, so concatenating the two files gives a labelled
  evaluation set
- `results/_counts_<baseline>.json` — machine-readable counts
- `results/_vcf_mc_stats.json` — VCF coverage and the SO terms binned as `other`

## Review-status star ladder

| stars | ClinVar review status |
|---|---|
| 0 | no assertion criteria provided *(excluded from cohorts)* |
| 1 | criteria provided, single submitter · criteria provided, conflicting |
| 2 | criteria provided, multiple submitters, no conflicts |
| 3 | reviewed by expert panel |
| 4 | practice guideline |

## Citing

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21766106.svg)](https://doi.org/10.5281/zenodo.21766106)

Cite the **archived release**, not this repository URL. A repository link is not
a stable reference: re-running the pipeline against a newer ClinVar release
legitimately changes the counts, so a bare link can point at numbers that differ
from the ones you read.

> Barra, G. B. *vus-hindsight: a retrospective ClinVar VUS reclassification
> benchmark* (V1.0.0) [Data set]. Zenodo.
> <https://doi.org/10.5281/zenodo.21766106>

Release `V1.0.0` is computed against the archived monthly
`variant_summary_2026-07.txt.gz` (2 July 2026), with the md5 of every input
recorded in [`results/transitions.md`](results/transitions.md). Because the
endpoint is an archived file rather than the rolling one, these counts can be
regenerated exactly — see below for why that distinction is not cosmetic.

Zenodo mints two DOIs: a *concept* DOI that always resolves to the newest
version, and a *version* DOI fixed to one release. The one above is what the
repository badge reports. When quoting specific counts, prefer the version DOI
for `V1.0.0` — shown on that release's Zenodo page — so the citation cannot
drift onto a later release with different numbers.

[`CITATION.cff`](CITATION.cff) carries the machine-readable metadata.

## Running it again

The workflow is **manual only** — Actions → *ClinVar VUS reclassification
benchmark* → **Run workflow**. It used to run automatically on any push touching
`scripts/`, which was right while the results were being established and is
wrong now that they are published: ClinVar ships a new `variant_summary`
monthly, so an unrelated code change would silently re-fetch a newer release and
rewrite the committed counts underneath anyone relying on them.

When you do regenerate, tag a release first so the previous numbers stay
citable.

**Always pin the endpoint if the numbers will be quoted.** The *Current month*
input points the endpoint at an archived monthly (`YYYY-MM`) instead of the
rolling `variant_summary.txt.gz`. Locally: `CURRENT_MONTH=2026-07
scripts/run_all.sh`.

This is not a convenience. NCBI **overwrites** `variant_summary.txt.gz` in
place and archives only one snapshot per month, so a result computed against the
rolling file is *not reproducible from NCBI at all* once it is superseded — the
bytes are simply gone. Only the monthly archives persist.

The distinction is easy to underestimate. The first runs of this benchmark used
the rolling file, which on that day was the release of 28 July 2026; the
archived monthly for the same month is dated 2 July 2026. Twenty-six days apart,
and the counts differ accordingly — 4,771 vs 4,735 VUS → P/LP for the 2021-06
baseline, 1,612 vs 1,577 in the missense ≥2★ stratum. Those earlier figures
survive only in this repository's git history; they cannot be regenerated.

The consequence VCF has the same property and the same fix. `vcf_GRCh38/`
carries both a rolling `clinvar.vcf.gz` and a dated `clinvar_YYYYMMDD.vcf.gz`
with identical content; the pipeline takes the **dated** one and refuses to fall
back to the rolling name, and `VCF_DATE=YYYYMMDD` pins an exact release. Older
dated VCFs move to `vcf_GRCh38/archive_2.0/<YEAR>/`.

Everything published from `V1.0.0` onward uses an archived endpoint for exactly
this reason.

## License

See [LICENSE](LICENSE).
