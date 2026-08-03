# Contamination audit — baseline 2021-06

Whether a predictor could already have been told this benchmark's answer. Two things decide that, and they are independent:

- **When** its training data was fixed (`training_cutoff`).
- **Whether** curated clinical labels entered the model at all (`label_exposure`), and in what role.

A sequence-only model has no clinical labels to memorise, so its release date barely matters. A model fit on ClinVar P/LP labels is exposed in proportion to how recent its snapshot was. Ranking on dates alone would score those two the same, which is wrong.

Window: **4,735** VUS → P/LP reclassifications over 61 months.

## Verdicts

| predictor | verdict | label exposure | cutoff | labels exposed |
|---|---|---|---|---|
| AlphaMissense | MEASURED LEAK | evaluation_only | — | **measured — see below** |
| BayesDel | DIRECT / UNVERIFIED | training_labels | — | — |
| MutationTaster2 | DIRECT / UNVERIFIED | training_labels | — | — |
| MutationTaster2021 | DIRECT / UNVERIFIED | training_labels | — | — |
| REVEL | DIRECT / UNVERIFIED | training_labels | — | — |
| VEST (4) | DIRECT / UNVERIFIED | training_labels | — | — |
| CADD | INDIRECT / UNVERIFIED | evaluation_only | — | — |
| PrimateAI | INDIRECT / UNVERIFIED | evaluation_only | — | — |
| FATHMM | DIRECT / CLEAN | training_labels | 2013-04 | 0 |
| PolyPhen-2 (HumDiv) | DIRECT / CLEAN | training_labels | 2011-04 | 0 |
| PolyPhen-2 (HumVar) | DIRECT / CLEAN | training_labels | 2011-04 | 0 |
| ESM-1b | LABEL-FREE | none | 2018-03 | 0 |
| EVE | LABEL-FREE | none | 2020-04 | 0 |
| MutationAssessor (r3) | LABEL-FREE | none | — | — |
| PROVEAN | LABEL-FREE (score) | threshold_only | 2011-08 | 0 |
| SIFT | LABEL-FREE | none | — | — |

**8 of 16** carry no contamination caveat for this baseline:

- FATHMM — DIRECT / CLEAN
- PolyPhen-2 (HumDiv) — DIRECT / CLEAN
- PolyPhen-2 (HumVar) — DIRECT / CLEAN
- ESM-1b — LABEL-FREE
- EVE — LABEL-FREE
- MutationAssessor (r3) — LABEL-FREE
- PROVEAN — LABEL-FREE (score)
- SIFT — LABEL-FREE

## Measured exposure — AlphaMissense

The only entry whose exposure was measured rather than inferred from a stated date.

- Method: Intersection of the vus-hindsight missense cohort against the 82,872 variants of the paper's Supplementary Data S5 — the nominal ClinVar benchmark list.

- Reclassified arm: **531 / 2883 = 18.42%**
- Control arm: 1 / 25000 = 0.004%
- Odds ratio: 5644 (Fisher, p < 1e-300)
- 531/531 appear in S5 with label=1 (pathogenic); zero as benign

| horizon | overlap |
|---|---|
| h18 | 527 / 589 = 89.5% |
| h36 | 3 / 1112 = 0.27% |
| h61 | 1 / 1182 = 0.08% |

The cliff between 18 and 36 months places DeepMind's ClinVar snapshot around end-2022: it holds almost every reclassification up to ~Dec 2022 and essentially none after.

**Scope.** Evaluation and calibration exposure, not weights. Weights were fit on population frequency. But the 531 sat in the set where AlphaMissense's performance was reported, and am_class descends directly from thresholds calibrated on that same snapshot.

## Still unresolved

8 predictors have clinical-label exposure and no sourced cutoff. An unverified tool is not a clean tool, it is an unmeasured one, so none of these may be reported as a clean baseline until `training_cutoff`, `source` and `verified` are filled in `predictors.yaml`.

- AlphaMissense (evaluation_only)
- BayesDel (training_labels)
- MutationTaster2 (training_labels)
- MutationTaster2021 (training_labels)
- REVEL (training_labels)
- VEST (4) (training_labels)
- CADD (evaluation_only)
- PrimateAI (evaluation_only)

Leakage figures are bracketed between the survival curve's measured time points rather than interpolated, and are upper bounds: using ClinVar does not mean using every reclassification in it.
