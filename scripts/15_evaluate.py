#!/usr/bin/env python3
"""Evaluate predictor scores on the benchmark, enforcing the contamination audit.

Positives are variants that were VUS at baseline and are P/LP now; negatives are
the missense controls that stayed VUS. Discrimination is reported per horizon,
because that is the axis contamination runs along: a predictor exposed to a
snapshot taken 18 months after the baseline is compromised at the 18-month
horizon and clean at 61.

The audit is enforced rather than merely printed. A predictor whose overlap test
came back EXPOSED gets its affected horizons marked, and the headline figure is
computed on the horizons that survive. A benchmark that reports a single
contaminated AUC and mentions the caveat in a footnote is worse than one that
refuses.

Scores are supplied per predictor, since this repository does not redistribute
them:

  --scores "NAME:path:id_column:score_column:direction"

`direction` is `high` when a larger score means more pathogenic, `low` when the
reverse (SIFT and PROVEAN score that way, and getting it backwards would silently
invert every AUC).

Usage:
  15_evaluate.py --scores "EVE:data/eve.csv:variant_id_hg38:score:high" \
                 --scores "SIFT:data/sift.csv:variant_id_hg38:sift:low"
"""

import argparse
import hashlib
import json
import os
import sys

import duckdb
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

RESULTS = "results"
MIN_PER_CLASS = 20


def md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def metrics(y, s):
    """AUROC and average precision, or None when a class is too thin to mean anything."""
    y = np.asarray(y)
    s = np.asarray(s, dtype=float)
    ok = ~np.isnan(s)
    y, s = y[ok], s[ok]
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    if n_pos < MIN_PER_CLASS or n_neg < MIN_PER_CLASS:
        return {
            "n_pos": n_pos,
            "n_neg": n_neg,
            "auroc": None,
            "auprc": None,
            "note": f"fewer than {MIN_PER_CLASS} in a class",
        }
    return {
        "n_pos": n_pos,
        "n_neg": n_neg,
        "auroc": round(float(roc_auc_score(y, s)), 4),
        "auprc": round(float(average_precision_score(y, s)), 4),
        "note": None,
    }


def headline(y, s, hz, bad_horizons):
    """Discrimination with the contaminated horizons dropped.

    Extracted from `main` because this is the number that gets published. Only
    positives carry a horizon; the negatives are the controls that stayed VUS
    and belong to no horizon at all, so excluding a horizon removes exposed
    positives and leaves the control arm intact. Dropping the controls too would
    empty the negative class, and a metric computed on the remainder would look
    like a result.
    """
    keep = [i for i, horizon in enumerate(hz) if horizon not in bad_horizons]
    return metrics([y[i] for i in keep], [s[i] for i in keep])


def load_audit():
    """Which predictors are exposed, and at which horizons, from the overlap tests."""
    path = os.path.join(RESULTS, "_overlap_tests.json")
    if not os.path.exists(path):
        return {}
    flagged = {}
    for r in json.load(open(path)):
        if r.get("verdict") != "EXPOSED":
            continue
        # A horizon counts as compromised when its overlap is materially above
        # the control rate for the same list.
        ctl = (r["by_arm"].get("still_vus") or {}).get("pct") or 0.0
        bad = [
            h["horizon"]
            for h in r["by_horizon"]
            if (h["pct"] or 0.0) > max(5.0 * ctl, 1.0)
        ]
        flagged[r["name"].split()[0].lower()] = {"list": r["name"], "horizons": bad}
    return flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="data/exports/vus_hindsight_for_am_join.csv")
    ap.add_argument(
        "--scores",
        action="append",
        required=True,
        help="name:path:id_column:score_column:direction(high|low)",
    )
    ap.add_argument(
        "--stratum",
        default="primary",
        help="'primary' (missense, >=2 stars), 'other', or 'all'",
    )
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    con = duckdb.connect()
    where = "" if args.stratum == "all" else f"AND stratum = '{args.stratum}'"
    con.execute(f"""
        CREATE TABLE export AS
        SELECT variant_id_hg38, arm, horizon_months, stratum, gene_symbol,
               CASE WHEN arm = 'vus_to_plp' THEN 1 ELSE 0 END AS y
        FROM read_csv('{args.export}', header=true, all_varchar=true)
        WHERE molecular_consequence = 'missense' {where}
    """)
    n_pos, n_neg = con.execute(
        "SELECT count(*) FILTER (WHERE y=1), count(*) FILTER (WHERE y=0) FROM export"
    ).fetchone()
    print(f"stratum '{args.stratum}': {n_pos:,} positives, {n_neg:,} negatives")

    flagged = load_audit()
    if flagged:
        print("\ncontamination flags carried over from the overlap tests:")
        for k, v in flagged.items():
            print(f"  {k}: horizons {v['horizons']} exposed via {v['list']}")

    out = []
    for spec in args.scores:
        name, path, id_col, score_col, direction = spec.rsplit(":", 4)
        if not os.path.exists(path):
            print(f"FATAL: {path} not found", file=sys.stderr)
            return 1
        if direction not in ("high", "low"):
            print(
                f"FATAL: direction for {name} must be high or low, got "
                f"{direction!r}. Guessing would silently invert the AUC.",
                file=sys.stderr,
            )
            return 1

        sign = 1.0 if direction == "high" else -1.0
        con.execute(f"""
            CREATE OR REPLACE TABLE sc AS
            SELECT "{id_col}" AS vid,
                   {sign} * TRY_CAST("{score_col}" AS DOUBLE) AS score
            FROM read_csv('{path}', header=true, all_varchar=true)
        """)
        rows = con.execute("""
            SELECT e.y, s.score, e.horizon_months
            FROM export e JOIN sc s ON e.variant_id_hg38 = s.vid
            WHERE s.score IS NOT NULL
        """).fetchall()
        covered = len(rows)
        total = n_pos + n_neg
        print(f"\n=== {name} ===")
        print(f"  scored {covered:,} / {total:,} ({100.0 * covered / total:.1f}%)")
        if not rows:
            print("  no overlap with the cohort — nothing to evaluate")
            continue

        y = [r[0] for r in rows]
        s = [r[1] for r in rows]
        hz = [r[2] for r in rows]

        overall = metrics(y, s)
        key = name.split()[0].lower()
        bad_h = set(flagged.get(key, {}).get("horizons", []))

        per_h = {}
        for h in sorted({x for x in hz if x != "still_vus"}, key=lambda v: int(v)):
            idx = [i for i, v in enumerate(hz) if v == h or y[i] == 0]
            per_h[h] = metrics([y[i] for i in idx], [s[i] for i in idx])
            per_h[h]["contaminated"] = h in bad_h

        # The headline excludes horizons the overlap test flagged. A single
        # number computed across a contaminated horizon is the thing this whole
        # project exists to avoid producing.
        clean = headline(y, s, hz, bad_h)

        if overall["auroc"] is not None:
            print(
                f"  all horizons : AUROC {overall['auroc']:.3f}  "
                f"AUPRC {overall['auprc']:.3f}"
            )
        for h, m in per_h.items():
            flag = "  <-- CONTAMINATED" if m["contaminated"] else ""
            if m["auroc"] is not None:
                print(
                    f"  +{h:>3} months : AUROC {m['auroc']:.3f}  "
                    f"AUPRC {m['auprc']:.3f}{flag}"
                )
            else:
                print(f"  +{h:>3} months : {m['note']}{flag}")
        if bad_h:
            if clean["auroc"] is not None:
                print(
                    f"  HEADLINE (excluding {sorted(bad_h)}): "
                    f"AUROC {clean['auroc']:.3f}  AUPRC {clean['auprc']:.3f}"
                )
            else:
                print(f"  HEADLINE: {clean['note']}")

        out.append(
            {
                "predictor": name,
                "file": os.path.basename(path),
                "md5": md5(path),
                "direction": direction,
                "covered": covered,
                "coverage_pct": round(100.0 * covered / total, 2),
                "overall": overall,
                "by_horizon": per_h,
                "contaminated_horizons": sorted(bad_h),
                "headline": clean if bad_h else overall,
            }
        )

    # --- report --------------------------------------------------------------
    L = [f"# Evaluation — stratum `{args.stratum}`\n"]
    L.append(
        f"Positives: **{n_pos:,}** variants that were VUS at baseline and "
        f"are P/LP now. Negatives: **{n_neg:,}** missense controls that "
        "stayed VUS.\n"
    )
    L.append(
        "Discrimination is reported **per horizon**, because that is the "
        "axis contamination runs along. A predictor exposed to a snapshot "
        "taken 18 months after the baseline is compromised at the 18-month "
        "horizon and clean at 61 — a single pooled number hides exactly "
        "that.\n"
    )
    if flagged:
        L.append(
            "Horizons flagged by the overlap tests are excluded from the "
            "headline figure rather than footnoted. Reporting one "
            "contaminated number with a caveat underneath is the failure "
            "this benchmark exists to prevent.\n"
        )

    L.append("| predictor | coverage | headline AUROC | AUPRC | excluded horizons |")
    L.append("|---|---|---|---|---|")
    for r in out:
        hl = r["headline"]
        auroc = f"{hl['auroc']:.3f}" if hl["auroc"] is not None else "—"
        auprc = f"{hl['auprc']:.3f}" if hl["auprc"] is not None else "—"
        exc = ", ".join(f"+{h}" for h in r["contaminated_horizons"]) or "none"
        L.append(
            f"| {r['predictor']} | {r['coverage_pct']:.1f}% | **{auroc}** "
            f"| {auprc} | {exc} |"
        )
    L.append("")

    for r in out:
        L.append(f"## {r['predictor']}\n")
        L.append(
            f"`{r['file']}`, md5 `{r['md5']}`; scores read as "
            f"`{r['direction']} = more pathogenic`; "
            f"{r['covered']:,} variants scored "
            f"({r['coverage_pct']:.1f}% of the stratum).\n"
        )
        L.append("| horizon | positives | negatives | AUROC | AUPRC | |")
        L.append("|---|---|---|---|---|---|")
        for h, m in r["by_horizon"].items():
            a = f"{m['auroc']:.3f}" if m["auroc"] is not None else "—"
            p = f"{m['auprc']:.3f}" if m["auprc"] is not None else "—"
            flag = "**contaminated**" if m["contaminated"] else ""
            L.append(
                f"| +{h} months | {m['n_pos']:,} | {m['n_neg']:,} "
                f"| {a} | {p} | {flag} |"
            )
        L.append("")

    L.append("## Caveats\n")
    L.append(
        "- Coverage varies between predictors, so AUROCs are not computed "
        "on identical variant sets. Compare with that in mind, or restrict "
        "to the intersection.\n"
    )
    L.append(
        "- Score direction is declared per predictor rather than inferred. "
        "Inferring it from the data would flip an AUC silently whenever a "
        "predictor genuinely performs below chance.\n"
    )
    L.append(
        "- The controls stayed VUS as of the endpoint, which is not the "
        "same as being benign. Some will yet be reclassified, which makes "
        "this a conservative estimate of discrimination rather than an "
        "inflated one.\n"
    )

    with open(os.path.join(RESULTS, f"evaluation_{args.stratum}.md"), "w") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(RESULTS, f"_evaluation_{args.stratum}.json"), "w") as fh:
        json.dump(
            {
                "stratum": args.stratum,
                "n_pos": n_pos,
                "n_neg": n_neg,
                "flagged": flagged,
                "predictors": out,
            },
            fh,
            indent=2,
        )
    print(f"\nwrote {os.path.join(RESULTS, f'evaluation_{args.stratum}.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
