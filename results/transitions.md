# ClinVar VUS reclassification — measured transitions

Generated 2026-08-03 from ClinVar `variant_summary` snapshots. Every count below is produced by `scripts/04_transitions.py` and reproducible with `scripts/run_all.sh`.

## Snapshots

| snapshot | file | GRCh38 variants (deduped) | classification column | review column |
|---|---|---|---|---|
| 2021-06 | `variant_summary_2021-06.txt.gz` | 926,800 | ClinicalSignificance | ReviewStatus |
| 2022-12 | `variant_summary_2022-12.txt.gz` | 1,588,306 | ClinicalSignificance | ReviewStatus |
| current | `variant_summary_2026-07.txt.gz` | 4,459,687 | ClinicalSignificance | ReviewStatus |

Molecular consequence is read from the `MC` (Sequence Ontology) field of the ClinVar GRCh38 VCF `clinvar_20260728.vcf.gz` — 4,458,175 VariationIDs, of which 4,438,223 carry an `MC` term. It is not inferred from HGVS.

## Baseline 2021-06 → current

Baseline VUS cohort (criteria provided): **382,704** variants. Excluded 15,983 VUS with review status *no assertion criteria provided*.

| current classification | n | % of baseline VUS |
|---|---|---|
| Still VUS | 299,725 | 78.32% |
| Conflicting | 59,298 | 15.49% |
| B/LB | 10,631 | 2.78% |
| Retired/absent | 8,285 | 2.16% |
| P/LP | 4,735 | 1.24% |
| Other | 30 | 0.01% |

### VUS → P/LP arm (2021-06)

**4,735** variants moved from Uncertain significance to Pathogenic/Likely pathogenic, across **1,100** distinct genes.

By molecular consequence (ClinVar VCF `MC` field):

| consequence | n |
|---|---|
| missense | 2,883 |
| frameshift | 591 |
| other | 452 |
| nonsense | 437 |
| splice | 336 |
| not_in_vcf | 36 |

`not_in_vcf` = 36 variants have no record in the GRCh38 VCF (typically no precise genomic placement). They are reported as their own row rather than folded into `other`.

*Diagnostic:* an independent derivation of consequence from HGVS agrees with the `MC` term for 4,350/4,699 (92.57%) of these variants. The published breakdown above uses `MC` alone.

By current review status:

| review status | stars | n |
|---|---|---|
| criteria provided, single submitter | 1 | 2,542 |
| criteria provided, multiple submitters, no conflicts | 2 | 1,758 |
| reviewed by expert panel | 3 | 423 |
| no assertion criteria provided | 0 | 12 |

**Hard stratum** — missense AND review status at least *criteria provided, multiple submitters* (≥2 stars): **1,577** variants across 506 genes.

## Baseline 2022-12 → current

Baseline VUS cohort (criteria provided): **620,907** variants. Excluded 16,277 VUS with review status *no assertion criteria provided*.

| current classification | n | % of baseline VUS |
|---|---|---|
| Still VUS | 532,723 | 85.80% |
| Conflicting | 57,962 | 9.34% |
| B/LB | 17,292 | 2.79% |
| Retired/absent | 7,841 | 1.26% |
| P/LP | 5,058 | 0.81% |
| Other | 31 | 0.01% |

### VUS → P/LP arm (2022-12)

**5,058** variants moved from Uncertain significance to Pathogenic/Likely pathogenic, across **1,231** distinct genes.

By molecular consequence (ClinVar VCF `MC` field):

| consequence | n |
|---|---|
| missense | 2,698 |
| frameshift | 815 |
| nonsense | 569 |
| other | 492 |
| splice | 466 |
| not_in_vcf | 18 |

`not_in_vcf` = 18 variants have no record in the GRCh38 VCF (typically no precise genomic placement). They are reported as their own row rather than folded into `other`.

*Diagnostic:* an independent derivation of consequence from HGVS agrees with the `MC` term for 4,638/5,040 (92.02%) of these variants. The published breakdown above uses `MC` alone.

By current review status:

| review status | stars | n |
|---|---|---|
| criteria provided, single submitter | 1 | 3,365 |
| criteria provided, multiple submitters, no conflicts | 2 | 1,325 |
| reviewed by expert panel | 3 | 357 |
| no assertion criteria provided | 0 | 11 |

**Hard stratum** — missense AND review status at least *criteria provided, multiple submitters* (≥2 stars): **1,142** variants across 458 genes.

## Exact inputs

`variant_summary.txt.gz` and `clinvar.vcf.gz` are rolling filenames — the same URL serves a different release each month. To reproduce these exact counts, match the release stamp and md5 below; a newer release will legitimately give different numbers.

| role | file | bytes | release (Last-Modified) | md5 |
|---|---|---|---|---|
| archive 2026-07 | `variant_summary_2026-07.txt.gz` | 439,937,684 | Thu, 02 Jul 2026 04:05:02 GMT | `f03eea5e87f0ef5f696bbc958359fa78` |
| vcf | `clinvar_20260728.vcf.gz` | 193,012,905 | Tue, 28 Jul 2026 22:07:55 GMT | `28d247f7b297d3605a7b10079aa4467e` |
| archive 2021-06 | `variant_summary_2021-06.txt.gz` | 78,178,141 | Thu, 03 Jun 2021 04:05:02 GMT | `1f509ba1959d9cf882ee511572f4c185` |
| archive 2022-12 | `variant_summary_2022-12.txt.gz` | 145,316,022 | Thu, 01 Dec 2022 05:05:01 GMT | `5e08de585ae392186ae5c3e2a1748003` |

## Reproduce

```bash
scripts/run_all.sh
```

Per-variant records: `results/reclassified_pathogenic.tsv` (VUS → P/LP) and `results/reclassified_benign.tsv` (VUS → B/LB), identical schema. The benign arm supplies the negatives — discrimination cannot be measured from the pathogenic arm alone — so concatenating the two gives a labelled evaluation set.
