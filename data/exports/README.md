# `vus_hindsight_for_am_join.csv`

Flat export of the vus-hindsight cohort for external contamination analysis — joining predictor scores against variants whose ClinVar label changed, and against controls whose label did not.

## Exact inputs

| role | file | release (Last-Modified) | md5 |
|---|---|---|---|
| vcf | `clinvar_20260728.vcf.gz` | Tue, 28 Jul 2026 22:07:55 GMT | `28d247f7b297d3605a7b10079aa4467e` |
| archive 2021-06 | `variant_summary_2021-06.txt.gz` | Thu, 03 Jun 2021 04:05:02 GMT | `1f509ba1959d9cf882ee511572f4c185` |
| archive 2022-12 | `variant_summary_2022-12.txt.gz` | Thu, 01 Dec 2022 05:05:01 GMT | `5e08de585ae392186ae5c3e2a1748003` |
| archive 2024-06 | `variant_summary_2024-06.txt.gz` | Thu, 06 Jun 2024 04:05:16 GMT | `b1694d6443cf38ad187987c447e9bcd7` |
| archive 2026-07 | `variant_summary_2026-07.txt.gz` | Thu, 02 Jul 2026 04:05:02 GMT | `f03eea5e87f0ef5f696bbc958359fa78` |

Note that the endpoint is the **archived monthly** `variant_summary_2026-07.txt.gz` dated 2 July 2026, not the rolling `variant_summary.txt.gz` that NCBI overwrites in place. The rolling file cannot be reproduced once superseded, so no figure here is derived from it.

CSV md5: `ff2b77cc65eca8a4a62714df19dea9e3`

## Arms

| arm | rows | definition |
|---|---|---|
| `vus_to_plp` | 4,735 | VUS with assertion criteria at 2021-06, P/LP at 2026-07 (+61 months) |
| `still_vus` | 25,000 | VUS at 2021-06, still VUS at 2026-07; **missense only** |

`vus_to_plp` is drawn from the 2021-06 cohort alone, not the union across baselines. A variant from a different baseline has no horizon on this timeline, and the horizon is the field a contamination analysis turns on — it says when the label first appeared, and therefore the earliest a predictor could have been told the answer.

## Columns

| column | notes |
|---|---|
| `variant_id_hg38` | `chr{chrom}_{pos}_{ref}_{alt}_hg38`, GRCh38, from ClinVar's VCF-normalised coordinates |
| `horizon_months` | 18 / 36 / 61 — the first endpoint at which the variant was P/LP; `still_vus` in the control arm |
| `stratum` | `primary` = missense **and** ≥2 gold stars; `other` otherwise |
| `gold_stars` | 0–4 ClinVar review-status ladder |
| `date_last_evaluated` | ISO, empty when ClinVar reports none |

Rows lacking complete GRCh38 VCF coordinates are dropped: they cannot be joined on `variant_id_hg38`, which is the point of the export.

## Horizons

| horizon (months) | rows |
|---|---|
| 18 | 880 |
| 36 | 1,799 |
| 61 | 2,056 |

## Sampling

The missense `still_vus` control had **226,811** rows, above the 200,000 threshold, so it was reduced to 25,000 by **proportional stratified sampling on `gold_stars`**, largest-remainder to land on the target exactly.

Seed: `20260802`. Selection orders each stratum by `hash(VariationID || seed)` and takes the first *n* — deterministic, so re-running reproduces the identical draw without depending on an RNG implementation.

| gold_stars | available | sampled |
|---|---|---|
| 0 | 455 | 50 |
| 1 | 106,079 | 11,692 |
| 2 | 119,127 | 13,131 |
| 3 | 1,150 | 127 |
