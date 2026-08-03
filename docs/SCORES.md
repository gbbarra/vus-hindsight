# Getting predictor scores onto this benchmark

`15_evaluate.py` asks for very little: a CSV with an ID column and a score
column, where the ID is `chr{chrom}_{pos}_{ref}_{alt}_hg38` on GRCh38.

```csv
variant_id_hg38,score
chr1_925969_C_T_hg38,0.9124
```

That format is deliberate — it is the same key AlphaMissense's supplementary
data uses, which is what made the overlap in `results/overlap_tests.md`
measurable rather than arguable. Nothing else about a score file matters.

This repository does not redistribute scores. Every tool below has its own
licence, and several forbid it.

## The eight tools this benchmark can evaluate without a caveat

From `results/contamination_audit.md`, at the 2021-06 baseline:

| tool | verdict | in dbNSFP | native key |
|---|---|---|---|
| SIFT | LABEL-FREE | yes | genomic |
| PolyPhen-2 HumDiv | DIRECT / CLEAN | yes | genomic |
| PolyPhen-2 HumVar | DIRECT / CLEAN | yes | genomic |
| FATHMM | DIRECT / CLEAN | yes | genomic |
| PROVEAN | LABEL-FREE (score) | yes | protein |
| MutationAssessor | LABEL-FREE | yes | genomic |
| EVE | LABEL-FREE | 4.4a and later | **protein** |
| ESM-1b | LABEL-FREE | recent builds only | **protein** |

The `native key` column is the practical problem. EVE and ESM-1b are published
against UniProt accession plus amino-acid position, not chromosome and
coordinate. Mapping protein positions back to the genome means choosing a
transcript per gene, handling the ones where the canonical transcript changed
between Ensembl releases, and reversing the codon — a whole second pipeline,
with its own failure modes, none of which are visible in the output. dbNSFP has
already done that mapping. Where your build carries `EVE_score` and `ESM1b_score`,
take them from there.

## dbNSFP

dbNSFP is a precomputed table of every possible non-synonymous SNV in the human
exome — roughly 85–120 million rows depending on version — with forty-odd
predictor scores side by side, keyed on both assemblies. It is the shortest path
from "I want to evaluate SIFT" to a score file.

- Paper: Liu et al., *Genome Medicine* 2020, doi:10.1186/s13073-020-00803-9
  (dbNSFP v4). The landing page has always been the Liu lab's
  `sites.google.com/site/jpopgen/dbNSFP` page, which links whichever mirror is
  current. **I could not reach it from the sandbox this was written in, so treat
  the URL as a starting point rather than a verified one** — the DOI is the
  stable anchor.
- Releases come in `a` and `c` flavours (`dbNSFP4.9a`, `dbNSFP4.9c`). The `c`
  build omits scores whose licences forbid commercial use; the `a` build is the
  complete one for academic work.
- The download is a zip of one gzipped TSV per chromosome, tens of gigabytes.
  The converter takes a glob, so there is no need to concatenate them.
- The zip also contains a readme listing every column and what it means. That
  readme is the authority on your specific build — not this document, and not
  the converter's alias table.

Other routes produce the same columns and work equally well: the Ensembl VEP
dbNSFP plugin, or ANNOVAR's `dbnsfp` annotation. The converter only needs a TSV
with dbNSFP's column names in it.

### Which version

Any 4.x or 5.x release works. Prefer a recent one for two reasons: EVE arrived
in 4.4a and ESM-1b later still, and the sequence databases behind SIFT and
PROVEAN are refreshed with each build.

That second point has a consequence worth recording. SIFT and PROVEAN have no
training step — the score is a function of the alignment available *at scoring
time*. So for those tools the dbNSFP version **is** the effective date anchor,
and `predictors.yaml` should say which one you used:

```yaml
  - name: SIFT
    scored_from: dbNSFP4.9a
```

`results/_dbnsfp_conversion.json` records the exact source path of every run, so
the version is recoverable after the fact.

## Converting

Look at the file first — the same discipline `03_headers.py` applies to ClinVar:

```bash
python3 scripts/16_dbnsfp_to_scores.py --peek 'data/dbNSFP4.9a_variant.chr1.gz'
```

That prints every column, which pair of them holds GRCh38 and why, and which
predictors your build actually carries. Then convert:

```bash
python3 scripts/16_dbnsfp_to_scores.py \
  --dbnsfp 'data/dbNSFP4.9a_variant.chr*.gz' \
  --export data/exports/vus_hindsight_for_am_join.csv \
  --out-dir data/scores
```

One pass over dbNSFP produces every score file at once — reading forty gigabytes
once per predictor is not a reasonable ask — and each file is semi-joined to the
cohort, so the output is thousands of rows rather than a hundred million. The
run ends by printing the exact `15_evaluate.py` invocation for what it wrote.

### Rankscores are the default

dbNSFP ships `*_rankscore` and `*_converted_rankscore` next to every raw score,
all oriented the same way: larger is more damaging. The `converted_` prefix
marks precisely the tools whose raw score runs the other way — SIFT, FATHMM,
PROVEAN.

AUROC and AUPRC depend only on ranking, and a rankscore is a monotone transform
of its raw score, so using them changes no number this benchmark reports. What
it removes is the one mistake that inverts a result with no visible symptom: a
sign backwards. A predictor evaluated with the wrong direction does not crash or
look strange, it just reports 0.12 instead of 0.88, and 0.12 is a number one can
publish.

`--raw` emits the raw values instead, with each tool's direction taken from its
own publication and passed through to the evaluator explicitly. Raw scores carry
one value per transcript, separated by `;`; `--aggregate damaging` (the default)
keeps the most damaging across transcripts, `--aggregate mean` averages them.

### The build guard

dbNSFP carries both assemblies, and which columns hold GRCh38 depends on the
major version — 4.x and 5.x put it in `#chr` + `pos(1-based)` with GRCh37 in the
`hg19_` aliases, 3.x does the reverse. The converter detects this from which
alias column is present and refuses to run if neither is, because a wrong
coordinate pair produces IDs that join to nothing, and an empty join is
indistinguishable from a predictor that simply does not cover the cohort. It
also stops if the join comes back empty after a successful detection: dbNSFP
covers essentially every possible missense change, so zero overlap with a
missense cohort means a broken key, never absence of coverage.

This is the same guard `14_overlap_test.py` applies to published evaluation
lists, for the same reason. It is worth being blunt about why: in a
contamination analysis, a silent zero reads as *clean*. That is the most
dangerous direction for an error to fail in, so both scripts treat it as an
error rather than a result.

## EVE and ESM-1b when your dbNSFP build lacks them

Both publish precomputed scores for essentially every missense variant in their
coverage, keyed on protein:

- **EVE** — Frazer et al., *Nature* 2021, doi:10.1038/s41586-021-04043-8. Bulk
  download from the project site (`evemodel.org`). Covers ~3,200 genes, so
  expect coverage of this cohort well below the other tools; that is a property
  of EVE, not of the join, and `results/dbnsfp_conversion.md` reports coverage
  per predictor so the difference is visible rather than assumed.
- **ESM-1b** — Brandes et al., *Nature Genetics* 2023,
  doi:10.1038/s41588-023-01465-0. Precomputed log-likelihood ratios for all
  missense variants across ~42,000 UniProt proteins, distributed through the
  Ntranos lab's Hugging Face resources.

Neither URL was reachable from the sandbox this was written in. The DOIs are the
anchors; the download locations should be confirmed against the papers.

Going that route means writing the protein-to-genome mapping yourself. If you
do, key it on the same transcript set ClinVar used for the cohort, and check the
result the way the converter does — a coverage number near zero is a mapping
bug, not a finding.

## Checking a score file before trusting it

The converter prints, per predictor, the number of variants scored, coverage as
a share of the cohort, the score range and median, and the split across the two
arms. Four things are worth reading rather than skipping:

1. **Range and sign.** A raw ESM-1b file should be mostly negative; a PolyPhen-2
   file should sit in 0–1. A range that looks wrong means the column is not what
   the alias table assumed, and the direction that gets passed to the evaluator
   is then wrong too.
2. **Coverage.** SIFT and PolyPhen-2 should cover nearly the whole missense
   cohort. A few percent means a broken join that happened to find something.
3. **The arm split.** Both `vus_to_plp` and `still_vus` should appear. A file
   covering only one arm cannot produce a meaningful AUROC, and
   `15_evaluate.py` will refuse below twenty per class rather than report a
   number computed on three variants.
4. **Which predictors were absent.** They are listed by name. Absent is recorded
   as absent — nothing is substituted, and a column that exists but holds
   nothing for this cohort produces no file at all rather than an empty one.

## Then evaluate

```bash
python3 scripts/15_evaluate.py \
  --scores "SIFT:data/scores/sift.csv:variant_id_hg38:score:high" \
  --scores "PolyPhen-2_HumDiv:data/scores/polyphen2_hdiv.csv:variant_id_hg38:score:high"
```

The evaluator reads `results/_overlap_tests.json` and excludes any horizon a
tool was measured to be exposed at from that tool's headline figure. Run
`14_overlap_test.py` first for any predictor that published the variants it was
evaluated on.
