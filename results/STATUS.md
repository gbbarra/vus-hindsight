# Provenance of the results in this directory

The counts in [`transitions.md`](transitions.md) were produced by
`scripts/run_all.sh` running on a GitHub-hosted Actions runner, and committed
straight from that run. `run_log.txt` is the complete, unedited log of the run
that generated them — every download, every header, every query result.

Nothing in this directory is an estimate or a placeholder. If a number appears
here, it came out of the pipeline.

## Reproducing

Actions → *ClinVar VUS reclassification benchmark* → **Run workflow**, or
locally:

```bash
pip install duckdb
scripts/run_all.sh
```

Snapshots are re-fetched from NCBI each run and the filenames are resolved from
the live directory listing, so re-running against a newer ClinVar release will
shift the counts — that is expected. The run log records exactly which files a
given set of numbers came from.

## Why the pipeline runs in CI

The development sandbox this was built in routes outbound HTTPS through an
egress proxy that refuses `ftp.ncbi.nlm.nih.gov` with a 403 at the CONNECT
stage, along with every other NCBI host and `ftp.ebi.ac.uk`. DNS resolved
correctly, so it was a policy decision rather than a network fault. No mirror,
alternate port, or third-party copy of ClinVar was substituted — provenance for
a figure a reviewer can check has to trace to NCBI directly. GitHub-hosted
runners have unrestricted egress, so the benchmark runs there instead.

That constraint is what `.github/workflows/benchmark.yml` exists to route
around, and it is why the workflow commits its own results back.

## Two things the first CI runs surfaced

**ClinVar's archive is split by age.** Only about the last 18 months of
`variant_summary_*.txt.gz` sit loose in `tab_delimited/archive/`; everything
older is filed under `archive/<YEAR>/`. The first run failed rather than guess a
path, which is the intended behaviour — it printed the months that actually
exist and stopped.

**`variant_summary` did not get renamed columns.** As of the 2026-07 release it
still uses `ClinicalSignificance` and `ReviewStatus`; the germline/somatic split
added columns (`SomaticClinicalImpact`, `Oncogenicity`, `SCVsForAggregate*`)
rather than renaming these, for 43 total. `scripts/schema.py` resolved this from
the real header, and the header of every snapshot is printed into the run log
before any query runs.
