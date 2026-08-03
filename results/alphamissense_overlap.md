# AlphaMissense: measured exposure to this benchmark's labels

AlphaMissense states that a ClinVar subset was used for model selection and hyperparameter optimisation, and that the thresholds behind `am_class` were calibrated for 90% precision on a ClinVar snapshot. It does not state **which** release.

That is measurable rather than merely arguable, because the paper publishes the list: Supplementary Data S5, **82,872** variants keyed by `chr{chrom}_{pos}_{ref}_{alt}_hg38` — the same key this benchmark exports.

## Overlap

Missense only on both sides: S5 is a missense benchmark, so including other consequences would deflate the overlap for a reason unrelated to contamination.

| arm | in S5 | total | rate |
|---|---|---|---|
| `still_vus` | 1 | 25,000 | **0.004%** |
| `vus_to_plp` | 531 | 2,883 | **18.418%** |

Fisher exact, reclassified versus control: **OR = 5,644**, p = 0.

The control is what makes this a signal rather than an artefact. `still_vus` variants were VUS at baseline and still are — they are the same kind of variant, in the same genes, drawn from the same release. If the overlap simply reflected two large sets intersecting, the control would show a comparable rate.

## Label of the matches

| S5 label | matches |
|---|---|
| 1.0 | 531 |

## By horizon — dating the snapshot

Reclassifications are stratified by when the label **first appeared**. A snapshot taken at date D shows high overlap for horizons before D and near-zero after, so the position of the cliff dates it.

| horizon | in S5 | total | rate |
|---|---|---|---|
| +18 months | 527 | 589 | **89.47%** |
| +36 months | 3 | 1,112 | **0.27%** |
| +61 months | 1 | 1,182 | **0.08%** |

## Strata

| arm | stratum | in S5 | total | rate |
|---|---|---|---|---|
| `still_vus` | other | 0 | 11,742 | 0.000% |
| `still_vus` | primary | 1 | 13,258 | 0.008% |
| `vus_to_plp` | other | 272 | 1,306 | 20.827% |
| `vus_to_plp` | primary | 259 | 1,577 | 16.424% |

## What this does and does not show

**It is exposure through evaluation and calibration, not through weights.** AlphaMissense's weights were fit on population-frequency weak labels, and the authors say explicitly that they avoid circularity by not training on human annotation. Nothing here contradicts that.

What it shows is narrower and still consequential: variants whose ClinVar label changed after this benchmark's baseline were present in the set where AlphaMissense's performance was reported, and in the snapshot against which the `am_class` thresholds were calibrated. `am_class` is therefore downstream of a set containing answers this benchmark treats as unknown at baseline.

The practical consequence is bounded and specific: for the shortest horizon, an evaluation of AlphaMissense on this cohort is substantially an evaluation on data it was tuned against. For the longer horizons it is not.

## Inputs

| file | md5 |
|---|---|
| `vus_hindsight_for_am_join.csv` | `ff2b77cc65eca8a4a62714df19dea9e3` |
| `science.adg7492_data_s5.csv` | `27913b9c4aab674a6c60aa1778eba428` |

Supplementary Data S5 accompanies Cheng et al., *Science* 2023, doi:10.1126/science.adg7492. It is not redistributed here; the md5 above identifies the file used so the analysis can be checked against the same bytes.

Matched variants: `alphamissense_overlap_matches.csv`.
