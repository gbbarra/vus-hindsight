# Overlap tests against published evaluation sets

Any predictor that publishes the variants it was evaluated or calibrated on can be tested the same way. Each test yields a magnitude — how much of the reclassified arm is in the list, against a control that stayed VUS — and a date, from the horizon at which the overlap collapses.

| evaluation set | rows | reclassified | control | OR | verdict |
|---|---|---|---|---|---|
| AlphaMissense S5 (ClinVar benchmark) | 82,872 | 531 / 2,883 (18.418%) | 1 / 25,000 (0.004%) | 5,644 | **EXPOSED** |
| AlphaMissense S6 | 2,601 | 15 / 2,883 (0.520%) | 26 / 25,000 (0.104%) | 5 | **MINIMAL** |
| AlphaMissense S7 | 410 | 0 / 2,883 (0.000%) | 0 / 25,000 (0.000%) | nan | **UNUSABLE (coordinate build mismatch)** |

## AlphaMissense S5 (ClinVar benchmark)

`science.adg7492_data_s5.csv`, md5 `27913b9c4aab674a6c60aa1778eba428` — 82,872 rows, 82,872 keyed on GRCh38 and 0 on GRCh37.

| horizon | in list | total | rate |
|---|---|---|---|
| +18 months | 527 | 589 | **89.47%** |
| +36 months | 3 | 1,112 | **0.27%** |
| +61 months | 1 | 1,182 | **0.08%** |

Labels carried by the matches: `1.0` × 531

## AlphaMissense S6

`science.adg7492_data_s6.csv`, md5 `a934a63f2c5ecd46a8859d769ac88c16` — 2,601 rows, 2,601 keyed on GRCh38 and 0 on GRCh37.

| horizon | in list | total | rate |
|---|---|---|---|
| +18 months | 3 | 589 | **0.51%** |
| +36 months | 3 | 1,112 | **0.27%** |
| +61 months | 9 | 1,182 | **0.76%** |

Labels carried by the matches: `1` × 14, `0` × 1

## AlphaMissense S7

`science.adg7492_data_s7.csv`, md5 `f03bd3fc628a875f4211248c7fa6f786` — 410 rows, 0 keyed on GRCh38 and 410 on GRCh37.

**This list cannot be tested.** Its identifiers are predominantly GRCh37, and this benchmark keys on GRCh38, so the join finds nothing for a reason that has nothing to do with contamination. Reporting the resulting 0% as absence of exposure would be the most misleading outcome available, so it is refused instead. Lift the list over to GRCh38 to test it.

## Reading these

A high rate in the reclassified arm alongside a near-zero rate in the control is exposure. Comparable rates in both would instead mean the list simply covers a lot of variants.

A cliff across horizons dates the snapshot: the label was already in ClinVar when the list was built for horizons before the cliff, and had not appeared yet for horizons after it.
