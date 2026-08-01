# ClinVar VUS reclassification — measured transitions

Generated 2026-08-01 from ClinVar `variant_summary` snapshots. Every count below is produced by `scripts/04_transitions.py` and reproducible with `scripts/run_all.sh`.

## Snapshots

| snapshot | file | GRCh38 variants (deduped) | classification column | review column |
|---|---|---|---|---|
| 2021-06 | `variant_summary_2021-06.txt.gz` | 926,800 | ClinicalSignificance | ReviewStatus |
| 2022-12 | `variant_summary_2022-12.txt.gz` | 1,588,306 | ClinicalSignificance | ReviewStatus |
| current | `variant_summary.txt.gz` | 4,478,492 | ClinicalSignificance | ReviewStatus |

Molecular consequence is read from the `MC` (Sequence Ontology) field of the ClinVar GRCh38 VCF `clinvar.vcf.gz` — 4,458,175 VariationIDs, of which 4,438,223 carry an `MC` term. It is not inferred from HGVS.

## Baseline 2021-06 → current

Baseline VUS cohort (criteria provided): **382,704** variants. Excluded 15,983 VUS with review status *no assertion criteria provided*.

| current classification | n | % of baseline VUS |
|---|---|---|
| Still VUS | 299,002 | 78.13% |
| Conflicting | 59,970 | 15.67% |
| B/LB | 10,646 | 2.78% |
| Retired/absent | 8,285 | 2.16% |
| P/LP | 4,771 | 1.25% |
| Other | 30 | 0.01% |

### VUS → P/LP arm (2021-06)

**4,771** variants moved from Uncertain significance to Pathogenic/Likely pathogenic, across **1,102** distinct genes.

By molecular consequence (ClinVar VCF `MC` field):

| consequence | n |
|---|---|
| missense | 2,921 |
| frameshift | 591 |
| other | 456 |
| nonsense | 433 |
| splice | 334 |
| not_in_vcf | 36 |

`not_in_vcf` = 36 variants have no record in the GRCh38 VCF (typically no precise genomic placement). They are reported as their own row rather than folded into `other`.

*Diagnostic:* an independent derivation of consequence from HGVS agrees with the `MC` term for 4,382/4,735 (92.54%) of these variants. The published breakdown above uses `MC` alone.

By current review status:

| review status | stars | n |
|---|---|---|
| criteria provided, single submitter | 1 | 2,534 |
| criteria provided, multiple submitters, no conflicts | 2 | 1,790 |
| reviewed by expert panel | 3 | 435 |
| no assertion criteria provided | 0 | 12 |

**Hard stratum** — missense AND review status at least *criteria provided, multiple submitters* (≥2 stars): **1,612** variants across 510 genes.

## Baseline 2022-12 → current

Baseline VUS cohort (criteria provided): **620,907** variants. Excluded 16,277 VUS with review status *no assertion criteria provided*.

| current classification | n | % of baseline VUS |
|---|---|---|
| Still VUS | 531,679 | 85.63% |
| Conflicting | 58,916 | 9.49% |
| B/LB | 17,336 | 2.79% |
| Retired/absent | 7,841 | 1.26% |
| P/LP | 5,104 | 0.82% |
| Other | 31 | 0.01% |

### VUS → P/LP arm (2022-12)

**5,104** variants moved from Uncertain significance to Pathogenic/Likely pathogenic, across **1,240** distinct genes.

By molecular consequence (ClinVar VCF `MC` field):

| consequence | n |
|---|---|
| missense | 2,734 |
| frameshift | 824 |
| nonsense | 572 |
| other | 495 |
| splice | 461 |
| not_in_vcf | 18 |

`not_in_vcf` = 18 variants have no record in the GRCh38 VCF (typically no precise genomic placement). They are reported as their own row rather than folded into `other`.

*Diagnostic:* an independent derivation of consequence from HGVS agrees with the `MC` term for 4,679/5,086 (92.00%) of these variants. The published breakdown above uses `MC` alone.

By current review status:

| review status | stars | n |
|---|---|---|
| criteria provided, single submitter | 1 | 3,377 |
| criteria provided, multiple submitters, no conflicts | 2 | 1,354 |
| reviewed by expert panel | 3 | 362 |
| no assertion criteria provided | 0 | 11 |

**Hard stratum** — missense AND review status at least *criteria provided, multiple submitters* (≥2 stars): **1,169** variants across 466 genes.

## Exact inputs

`variant_summary.txt.gz` and `clinvar.vcf.gz` are rolling filenames — the same URL serves a different release each month. To reproduce these exact counts, match the release stamp and md5 below; a newer release will legitimately give different numbers.

| role | file | bytes | release (Last-Modified) | md5 |
|---|---|---|---|---|
| current | `variant_summary.txt.gz` | 441,573,728 | Tue, 28 Jul 2026 08:57:47 GMT | `476318456e1438c4d0d76a33f21e7350` |
| vcf | `clinvar.vcf.gz` | 193,012,905 | Tue, 28 Jul 2026 22:07:55 GMT | `28d247f7b297d3605a7b10079aa4467e` |
| archive 2021-06 | `variant_summary_2021-06.txt.gz` | 78,178,141 | Thu, 03 Jun 2021 04:05:02 GMT | `1f509ba1959d9cf882ee511572f4c185` |
| archive 2022-12 | `variant_summary_2022-12.txt.gz` | 145,316,022 | Thu, 01 Dec 2022 05:05:01 GMT | `5e08de585ae392186ae5c3e2a1748003` |

## Reproduce

```bash
scripts/run_all.sh
```

Per-variant records for the VUS → P/LP arm: `results/reclassified_pathogenic.tsv`.
