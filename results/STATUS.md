# Results status: BLOCKED — no counts produced

**There are no ClinVar-derived numbers in this repository.** The analysis has
not been run against real data. Nothing here is an estimate, a placeholder, or a
plausible-looking stand-in.

## What blocked it

The sandbox this was prepared in routes all outbound HTTPS through an egress
proxy that enforces an organization network policy. Every NCBI host required to
fetch ClinVar returns **HTTP 403 at the CONNECT stage** — the connection is
refused by policy before any request is made.

Probed 2026-07-31:

| host | result |
|---|---|
| `ftp.ncbi.nlm.nih.gov:443` | 403 CONNECT — policy denial |
| `www.ncbi.nlm.nih.gov:443` | 403 CONNECT — policy denial |
| `eutils.ncbi.nlm.nih.gov:443` | 403 CONNECT — policy denial |
| `api.ncbi.nlm.nih.gov:443` | 403 CONNECT — policy denial |
| `ftp.ebi.ac.uk:443` | 403 CONNECT — policy denial |
| `pypi.org:443` | 200 — reachable (DuckDB installed from here) |

DNS resolves `ftp.ncbi.nlm.nih.gov` correctly, so this is an egress policy
decision, not a network or DNS fault. The proxy's own documentation directs that
403 policy denials be reported rather than retried or routed around, so no
mirror, alternate port, or third-party copy of ClinVar was used — provenance for
a grant figure has to trace to NCBI directly.

`clinvar-public.s3.amazonaws.com` was probed and returns `NoSuchBucket`; it is
not an NCBI mirror.

## What to do

Recreate the environment with `ftp.ncbi.nlm.nih.gov` on the egress allowlist
(network policy is chosen when the environment is created — see
<https://code.claude.com/docs/en/claude-code-on-the-web>), then run:

```bash
pip install duckdb
scripts/run_all.sh
```

That produces `results/transitions.md`,
`results/reclassified_pathogenic.tsv`, and `results/_counts_*.json`, and
replaces this file's role. Expect the download step to dominate the runtime;
the analysis itself streams and is fast.

Running the same pipeline on a machine with ordinary internet access works
identically — the only requirement is reaching the ClinVar FTP host.

## What *has* been verified

The analysis logic is exercised end-to-end by `tests/test_pipeline.py` against a
synthetic fixture with known expected counts. All assertions pass, covering:

- header-driven column resolution across both ClinVar naming eras
  (`ClinicalSignificance`/`ReviewStatus` → `GermlineClassification`/`GermlineReviewStatus`)
- `Assembly = 'GRCh38'` filtering
- deduplication on `VariationID`
- classification bucketing into P/LP, B/LB, Still VUS, Conflicting, Other,
  Retired/absent
- exclusion of *no assertion criteria provided* from baseline cohorts
- the review-status star ladder, including the ≥2-star cutoff
- molecular-consequence derivation from HGVS
- per-variant TSV emission

Those are code-correctness checks on synthetic input. **They are not results and
imply nothing about ClinVar.**
