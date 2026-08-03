# Contamination audit — baseline 2021-06

Whether a predictor could already have been told this benchmark's answer. The labels are ClinVar reclassifications between the baseline and the endpoint; a model trained on data from inside that window may be recalling them rather than predicting them.

Window: **4,735** VUS → P/LP reclassifications over 61 months, from [`survival.md`](survival.md).

| tier | meaning |
|---|---|
| CLEAN | training cutoff at or before the baseline |
| PARTIAL | cutoff inside the window; some labels were visible |
| CONTAMINATED | cutoff at or beyond the endpoint |
| UNVERIFIED | no sourced cutoff — **not** the same as clean |


| predictor | tier | cutoff | labels potentially seen | uses ClinVar |
|---|---|---|---|---|
| AlphaMissense | UNVERIFIED | — | — | unknown |
| BayesDel | UNVERIFIED | — | — | unknown |
| CADD | UNVERIFIED | — | — | unknown |
| ESM-1b | UNVERIFIED | — | — | unknown |
| EVE | UNVERIFIED | — | — | unknown |
| FATHMM | UNVERIFIED | — | — | unknown |
| MutationAssessor | UNVERIFIED | — | — | unknown |
| MutationTaster | UNVERIFIED | — | — | unknown |
| PROVEAN | UNVERIFIED | — | — | unknown |
| PolyPhen-2 (HumDiv) | UNVERIFIED | — | — | unknown |
| PolyPhen-2 (HumVar) | UNVERIFIED | — | — | unknown |
| PrimateAI | UNVERIFIED | — | — | unknown |
| REVEL | UNVERIFIED | — | — | unknown |
| SIFT | UNVERIFIED | — | — | unknown |
| VEST (4) | UNVERIFIED | — | — | unknown |

**15 of 15 predictors have no sourced training cutoff.** Until those are filled in from the literature, this audit cannot say the benchmark is uncontaminated for them — and an unverified tool must not be reported as a clean baseline. Fill `training_cutoff`, `source` and `verified` in `predictors.yaml`.

Leakage is quoted as a range between the survival curve's measured time points rather than interpolated, so the bound comes from measurement rather than from a fitted line. It is an upper bound on exposure: a predictor may have used ClinVar without using every reclassification in it.
