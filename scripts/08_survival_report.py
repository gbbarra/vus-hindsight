#!/usr/bin/env python3
"""Render the fixed-cohort survival curve from results/_survival.json.

Writes results/survival.md plus two SVG charts. The charts are generated
without any plotting library so the pipeline keeps a single dependency.

Two panels rather than one: the still-VUS fraction lives near 100% while the
P/LP fraction lives near 1%, so drawing them on a shared axis would render the
interesting series as a flat line on the floor.
"""
import json
import os

RESULTS = "results"

INK = "#334155"
GRID = "#e2e8f0"
SERIES = {"still": "#64748b", "definitive": "#0284c7", "plp": "#dc2626",
          "hard": "#7c3aed"}


def line_chart(path, points, series, y_max, title, y_label, y_fmt="{:.0f}%"):
    """points: list of (x, {key: value}); series: list of (key, label, color)."""
    W, H = 760, 400
    ml, mr, mt, mb = 70, 150, 42, 56
    pw, ph = W - ml - mr, H - mt - mb
    xs = [p[0] for p in points]
    x_max = max(xs) if xs else 1

    def px(x):
        return ml + (x / x_max) * pw if x_max else ml

    def py(v):
        return mt + ph - (v / y_max) * ph if y_max else mt + ph

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" font-family="system-ui,-apple-system,'
         f'Segoe UI,Roboto,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{ml}" y="24" font-size="15" font-weight="600" '
         f'fill="{INK}">{title}</text>']

    # horizontal gridlines + y ticks
    for i in range(6):
        v = y_max * i / 5
        y = py(v)
        s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ml - 10}" y="{y + 4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="{INK}">{y_fmt.format(v)}</text>')

    # x ticks at each observed point
    for x in xs:
        s.append(f'<line x1="{px(x):.1f}" y1="{mt + ph}" x2="{px(x):.1f}" '
                 f'y2="{mt + ph + 5}" stroke="{INK}" stroke-width="1"/>')
        s.append(f'<text x="{px(x):.1f}" y="{mt + ph + 20}" font-size="11" '
                 f'text-anchor="middle" fill="{INK}">{x}</text>')
    s.append(f'<text x="{ml + pw / 2:.1f}" y="{H - 12}" font-size="12" '
             f'text-anchor="middle" fill="{INK}">months since the baseline '
             f'snapshot</text>')
    s.append(f'<text x="16" y="{mt + ph / 2:.1f}" font-size="12" fill="{INK}" '
             f'transform="rotate(-90 16 {mt + ph / 2:.1f})" '
             f'text-anchor="middle">{y_label}</text>')
    s.append(f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" '
             f'stroke="{INK}" stroke-width="1.5"/>')

    for idx, (key, label, color) in enumerate(series):
        pts = [(px(x), py(vals[key])) for x, vals in points]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                     for i, (x, y) in enumerate(pts))
        s.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" '
                 f'stroke-linejoin="round"/>')
        for x, y in pts:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ffffff" '
                     f'stroke="{color}" stroke-width="2.5"/>')
        ly = mt + 8 + idx * 22
        s.append(f'<line x1="{ml + pw + 16}" y1="{ly}" x2="{ml + pw + 40}" '
                 f'y2="{ly}" stroke="{color}" stroke-width="2.5"/>')
        s.append(f'<text x="{ml + pw + 46}" y="{ly + 4}" font-size="11.5" '
                 f'fill="{INK}">{label}</text>')

    s.append("</svg>")
    with open(path, "w") as fh:
        fh.write("\n".join(s))
    print(f"wrote {path}")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    src = os.path.join(RESULTS, "_survival.json")
    cohort_meta = os.path.join(RESULTS, "_survival_cohort.json")
    if not os.path.exists(src):
        raise SystemExit(f"{src} not found — run 07_survival.py first")
    points = json.load(open(src))
    meta = json.load(open(cohort_meta)) if os.path.exists(cohort_meta) else {}
    n = points[0]["cohort_size"]
    base_label = meta.get("baseline_label", "baseline")

    # Month 0 is definitional, not measured: at its own baseline the cohort is
    # 100% VUS by construction. Marked as such everywhere it appears.
    chart_points = [(0, {"still": 100.0, "plp": 0.0, "definitive": 0.0})]
    for p in points:
        chart_points.append((p["months_elapsed"],
                             {"still": p["pct_still_vus"], "plp": p["pct_p_lp"],
                              "definitive": p["pct_definitive"]}))

    line_chart(os.path.join(RESULTS, "survival_curve.svg"), chart_points,
               [("still", "still VUS", SERIES["still"])], 100.0,
               f"Survival of the {base_label} VUS cohort (n = {n:,})",
               "% of cohort still classified VUS")

    y_max = max(max(v["definitive"] for _, v in chart_points), 1.0) * 1.25
    line_chart(os.path.join(RESULTS, "reclassified_curve.svg"), chart_points,
               [("definitive", "resolved to P/LP or B/LB", SERIES["definitive"]),
                ("plp", "resolved to P/LP", SERIES["plp"])], y_max,
               f"Cumulative resolution of the {base_label} VUS cohort",
               "% of cohort resolved", y_fmt="{:.1f}%")

    L = [f"# Fixed-cohort survival curve — the {base_label} VUS cohort\n"]
    L.append(f"One cohort, **{n:,} variants**, classified *Uncertain "
             f"significance* with assertion criteria at {base_label} (GRCh38, "
             f"deduplicated on `VariationID`, excluding *no assertion criteria "
             f"provided*). The same variants are then looked up in each later "
             f"snapshot.\n")
    L.append("**Why hold the cohort fixed.** The transition analysis in "
             "[`transitions.md`](transitions.md) varies the *baseline* and holds "
             "the endpoint fixed, so a difference in reclassification rate is "
             "confounded with cohort composition — a later baseline contains many "
             "recently submitted, less mature variants. Here the denominator never "
             "changes across the three time points, so elapsed time is the only "
             "thing varying.\n")

    L.append("![Survival curve](survival_curve.svg)\n")
    L.append("![Cumulative resolution](reclassified_curve.svg)\n")

    L.append("## Measured points\n")
    L.append(table(
        ["snapshot", "months elapsed", "still VUS", "→ P/LP", "→ B/LB",
         "conflicting", "retired/absent"],
        [[p["endpoint_label"], p["months_elapsed"],
          f"{p['still_vus']:,} ({p['pct_still_vus']:.2f}%)",
          f"{p['p_lp']:,} ({p['pct_p_lp']:.2f}%)",
          f"{p['b_lb']:,}",
          f"{p['distribution'].get('Conflicting', 0):,}",
          f"{p['distribution'].get('Retired/absent', 0):,}"]
         for p in points]))
    L.append("")
    L.append("Month 0 is definitional rather than measured: the cohort is 100% "
             "VUS at its own baseline by construction. It anchors the curves but "
             "is not a data point.\n")

    L.append("## Evaluation material over time\n")
    L.append("How much usable benchmark material the cohort has yielded at each "
             "date — the hard stratum is missense **and** review status of at "
             "least *criteria provided, multiple submitters*.\n")
    L.append(table(["months elapsed", "→ P/LP", "distinct genes",
                    "hard stratum (missense, ≥2★)"],
                   [[p["months_elapsed"], f"{p['p_lp']:,}", f"{p['p_lp_genes']:,}",
                     f"{p['hard_stratum']:,}"] for p in points]))
    L.append("")

    # Point-in-time state, so a variant that reaches P/LP and is later disputed
    # can leave the bucket. Say so if it actually happens rather than implying
    # a monotone cumulative hazard.
    plps = [p["p_lp"] for p in points]
    if any(b < a for a, b in zip(plps, plps[1:])):
        L.append("> **Note:** the P/LP count is not monotonic across these "
                 "points. Each figure is the cohort's state *at that date*, not a "
                 "cumulative hazard — a variant reclassified to P/LP can later "
                 "move to conflicting and leave the bucket.\n")
    else:
        L.append("Each figure is the cohort's state *at that date* rather than a "
                 "cumulative hazard. Over these points the P/LP count happens to "
                 "increase monotonically, but nothing forces it to: a variant can "
                 "be reclassified and later disputed.\n")

    L.append("## Caveats\n")
    L.append("- The cohort is fixed, so this removes the composition confound "
             "between baselines — it does **not** remove ascertainment bias. "
             "Variants in well-studied genes still resolve faster.\n")
    L.append("- Molecular consequence, used for the hard stratum, comes from the "
             "current ClinVar VCF `MC` field. Consequence is a property of the "
             "variant rather than of the date, so applying it at every time point "
             "is intentional.\n")
    L.append("- Review status is read from each endpoint's own snapshot, so the "
             "hard stratum reflects what was true at that date.\n")

    out = os.path.join(RESULTS, "survival.md")
    with open(out, "w") as fh:
        fh.write("\n".join(L))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
