"""Loading one ClinVar variant_summary snapshot into DuckDB.

Shared by the transition analysis and the survival curve so both derive their
cohorts through identical code — a difference between the two would otherwise
be indistinguishable from a real finding.
"""
import gzip
import sys

from schema import bucket_sql, consequence_sql, resolve_columns, stars_sql


def header_of(path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.readline().rstrip("\n").lstrip("#").split("\t")


def reader_sql(path, cols):
    """A read_csv call with explicit column names.

    header=false + skip=1 + explicit names sidesteps the leading '#' that some
    snapshots put on the header line. quote/escape are disabled because ClinVar
    ships unbalanced double quotes inside unquoted fields.
    """
    names = ", ".join(f"'{c.replace(chr(39), chr(39) * 2)}'" for c in cols)
    return (
        f"read_csv('{path}', delim='\\t', header=false, skip=1, "
        f"names=[{names}], all_varchar=true, quote='', escape='', "
        f"ignore_errors=false)"
    )


def load_snapshot(con, alias, path, label):
    """Materialise one snapshot as `alias`: GRCh38 only, one row per VariationID."""
    cols = header_of(path)
    print(f"=== HEADER: {path} ===")
    print(f"{len(cols)} columns: {cols}")
    res = resolve_columns(cols)
    print(f"resolved: classification={res['classification']!r} "
          f"review_status={res['review_status']!r} "
          f"consequence={res['consequence']!r}")
    sys.stdout.flush()

    con.execute(f"CREATE OR REPLACE VIEW {alias}_raw AS "
                f"SELECT * FROM {reader_sql(path, cols)}")

    total = con.execute(f"SELECT count(*) FROM {alias}_raw").fetchone()[0]
    grch38 = con.execute(
        f"SELECT count(*) FROM {alias}_raw WHERE Assembly = 'GRCh38'"
    ).fetchone()[0]

    # Deduplicate on VariationID. Ordering by Name makes the pick deterministic.
    con.execute(f"""
        CREATE OR REPLACE TABLE {alias} AS
        SELECT
            TRY_CAST(VariationID AS BIGINT)          AS variation_id,
            {res['genesymbol']}                      AS gene,
            {res['name']}                            AS hgvs,
            {res['type']}                            AS var_type,
            {res['classification']}                  AS raw_class,
            {res['review_status']}                   AS raw_review,
            {bucket_sql(res['classification'])}      AS bucket,
            {stars_sql(res['review_status'])}         AS stars,
            {consequence_sql(res['name'], res['type'], res['consequence'])}
                                                     AS hgvs_consequence
        FROM {alias}_raw
        WHERE Assembly = 'GRCh38' AND TRY_CAST(VariationID AS BIGINT) IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY VariationID ORDER BY {res['name']}) = 1
    """)
    deduped = con.execute(f"SELECT count(*) FROM {alias}").fetchone()[0]
    print(f"[{label}] rows={total:,} GRCh38={grch38:,} "
          f"after dedupe on VariationID={deduped:,} "
          f"(collapsed {grch38 - deduped:,})")
    sys.stdout.flush()
    return {"rows_total": total, "rows_grch38": grch38, "rows_deduped": deduped,
            "classification_column": res["classification"],
            "review_column": res["review_status"],
            "consequence_source": res["consequence"] or "derived from HGVS in Name"}
