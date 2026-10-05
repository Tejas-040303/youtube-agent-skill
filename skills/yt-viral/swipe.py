#!/usr/bin/env python3
"""swipe.py - rank collected videos by how far each beat its OWN channel, then name the formula.

    python3 swipe.py collected.json
    python3 swipe.py collected.json --min 2.0 --json

Input is a list you collected - one object per video:

    [{"channel":"Some Channel","title":"...","views":412000,"url":"...","duration":613}, ...]

Raw view counts rank channel size, not ideas. A 400k video on a 2M-subscriber channel is a normal
Tuesday; a 400k video on a channel whose median is 30k is the thing worth studying. So every video
is scored as a MULTIPLE OF ITS OWN CHANNEL'S MEDIAN, which needs at least four videos per channel
to mean anything - the tool says so rather than quietly ranking on noise.

The formula comes from skills/yt-script/hooks.json, matched against the TITLE. It is a judgement
about the words on screen, not a claim about why the video worked.

BASE RATES. "13 of the outliers are The Question" means nothing on its own: if half of everything
collected is The Question, half of the outliers will be too. So each formula is reported with its
share of the outliers AND its share of every scored video, and the ratio between them (lift). A lift
near 1.0 means the outliers use that formula no more than the channel does anyway.
"""
import json, os, re, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMULAS = json.load(open(os.path.join(HERE, "..", "yt-script", "hooks.json")))["hooks"]

def classify(title):
    scored = []
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, title, re.I))
        if n: scored.append((n, f["name"]))
    scored.sort(reverse=True)
    return scored[0][1] if scored else "Unclassified"

def formula_rates(out, scored):
    """Each formula's share of the outliers next to its share of everything scored."""
    if not out or not scored: return []
    rows = []
    for f in sorted({r["formula"] for r in out}):
        n_out = sum(1 for r in out if r["formula"] == f)
        n_all = sum(1 for r in scored if r["formula"] == f)
        share_out, share_all = n_out / len(out), n_all / len(scored)
        rows.append({"formula": f, "outliers": n_out, "outlier_share": round(share_out, 3),
                     "all": n_all, "all_share": round(share_all, 3),
                     "lift": round(share_out / share_all, 2) if share_all else None})
    rows.sort(key=lambda r: (-r["outliers"], r["formula"]))
    return rows

def main():
    a = sys.argv[1:]
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    lo = float(a[a.index("--min") + 1]) if "--min" in a else 1.5
    files = [x for x in a if not x.startswith("--") and not re.match(r"^[\d.]+$", x)]
    if not files or not os.path.exists(files[0]): print(__doc__); sys.exit(1)
    rows = json.load(open(files[0]))
    if isinstance(rows, dict): rows = rows.get("videos", [])
    by = {}
    for r in rows: by.setdefault(r.get("channel", "?"), []).append(r)
    out, thin = [], []
    for ch, vids in by.items():
        views = [float(v.get("views", 0) or 0) for v in vids]
        med = statistics.median(views) if views else 0
        if len(vids) < 4:
            thin.append((ch, len(vids)))
            continue
        for v in vids:
            m = (float(v.get("views", 0) or 0) / med) if med else 0
            out.append({"channel": ch, "title": v.get("title", ""), "views": int(v.get("views", 0) or 0),
                        "median": int(med), "multiple": round(m, 2),
                        "formula": classify(v.get("title", "")), "url": v.get("url", "")})
    scored = out
    out = [r for r in scored if r["multiple"] >= lo]
    out.sort(key=lambda r: -r["multiple"])
    rates = formula_rates(out, scored)
    if as_json:
        print(json.dumps({"outliers": out, "formula_rates": rates, "skipped_thin_channels": thin},
                         indent=1)); return
    print(f"\n  {len(rows)} videos across {len(by)} channels, outliers at {lo}x or better\n")
    for r in out[:25]:
        print(f"    {r['multiple']:5.2f}x  {r['views']:>9,}  vs {r['median']:>9,} median   {r['channel'][:22]:<22} {r['title'][:52]}")
        print(f"            {r['formula']}")
    if not out: print("    nothing cleared the threshold - collect more per channel or lower --min")
    if thin:
        print(f"\n  skipped {len(thin)} channel(s) with under 4 videos collected - a median off one or")
        print( "  two videos is not a median: " + ", ".join(f"{c} ({n})" for c, n in thin[:6]))
    if rates:
        print(f"\n  formulas among the {len(out)} outliers, against all {len(scored)} scored videos")
        print("    outliers        all scored      lift  formula")
        for r in rates:
            print(f"    {r['outliers']:3d}  {r['outlier_share']:4.0%}       {r['all']:3d}  {r['all_share']:4.0%}"
                  f"      {r['lift']:4.2f}  {r['formula']}")
        print("    lift is outlier share / overall share. Near 1.0, the outliers use it no more than the")
        print("    channels do anyway; a high lift on a handful of videos is still a handful of videos.")
    print()

if __name__ == "__main__":
    main()
