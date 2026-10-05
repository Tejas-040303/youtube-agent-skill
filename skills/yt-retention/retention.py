#!/usr/bin/env python3
"""retention.py - read a YouTube Studio audience-retention export and find the leaks.

    python3 retention.py retention.csv
    python3 retention.py retention.csv --transcript transcript.srt   # names what was said at each drop
    python3 retention.py retention.csv --duration 45 --hook-seconds 3   # a Short
    python3 retention.py retention.csv --json

Get the file from Studio: Analytics -> a video -> Engagement -> the audience-retention chart ->
the download icon -> "Audience retention". Two columns, a position (percent or seconds) and a
percentage still watching.

It reports three things, because they are three different problems with three different fixes:
  HOOK LEAK    what you lost in the opening (the first 30 seconds unless --hook-seconds says otherwise)
  CLIFFS       single steep drops - a specific moment people left at
  SLIDE        the steady bleed rate across the flat middle

With --transcript it prints what you were saying at each cliff, which is the only version of this
report you can act on without scrubbing the video yourself.

PERCENT OR SECONDS. The position column can be either, and the two need different arithmetic. The
header decides when it says ("%", "percent", "sec", "time"). Otherwise positions past 100 are
seconds, and with --duration a column that ends at the video's length is seconds too - which is
what tells a 45-second Short in seconds apart from a percentage axis. With neither, it assumes
percent and says so. --axis overrides all of it.

SHORTS. A 30-second hook window is two thirds of a Short, so pass --hook-seconds. Retention over
100% is people watching again as the Short loops; the leak is still measured from the first point.
"""
import argparse, csv, json, os, sys

def load_csv(path):
    """(header, rows): the first row that is not two numbers, and every row that is."""
    header, rows = None, []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.reader(fh):
            nums = []
            for c in r:
                c = c.strip().replace("%", "").replace(",", "")
                try: nums.append(float(c))
                except ValueError: nums.append(None)
            vals = [n for n in nums if n is not None]
            if len(vals) >= 2: rows.append((vals[0], vals[1]))
            elif header is None and not rows and any(c.strip() for c in r): header = r
    return header, rows

def axis_of(header, xs, dur, forced=None):
    """('percent' | 'seconds', why). See PERCENT OR SECONDS in the module docstring."""
    if forced: return forced, "set by --axis"
    h = (header[0] if header else "").lower()
    if "%" in h or "percent" in h: return "percent", f"the header says {header[0].strip()!r}"
    if "sec" in h or "time" in h: return "seconds", f"the header says {header[0].strip()!r}"
    top = max(xs)
    if top > 100.5: return "seconds", f"positions run to {top:g}, past 100"
    if dur:
        # A percentage axis ends at ~100 whatever the length; a seconds axis ends at the length.
        if 0.8 * dur <= top <= 1.02 * dur and not 99.0 <= top <= 100.5:
            return "seconds", f"positions end at {top:g}, the length given by --duration"
        return "percent", f"positions end at {top:g}, not at the {dur:g}s duration"
    return "percent", "assumed - positions stay within 0-100 and there is no --duration to tell"

def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--transcript")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--hook-seconds", type=float, default=30.0)
    ap.add_argument("--axis", choices=["percent", "seconds"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    o = ap.parse_args()
    if o.help or not o.csv or not os.path.exists(o.csv): print(__doc__); sys.exit(0 if o.help else 1)

    header, rows = load_csv(o.csv)
    if len(rows) < 8: print("could not read at least 8 data points from that csv"); sys.exit(1)
    xs = [r[0] for r in rows]; ys = [r[1] for r in rows]
    dur = o.duration
    axis, why = axis_of(header, xs, dur, o.axis)
    pct_axis = axis == "percent"
    def at(x): return (x / 100.0 * dur) if (pct_axis and dur) else x
    timed = not pct_axis or bool(dur)
    start = ys[0] or 100.0
    hs = o.hook_seconds
    # HOOK: the first hook-seconds, or the first 10% when the axis is a percentage and we have no duration
    cutoff = hs if not pct_axis else (hs / dur * 100 if dur else 10.0)
    hook_end = min((y for x, y in rows if x <= cutoff), default=start)
    hook_leak = start - hook_end
    length = dur or (xs[-1] if not pct_axis else None)
    warnings = []
    if length and hs >= 0.5 * length:
        warnings.append(f"the {hs:g}s hook window is {hs / length:.0%} of this {length:g}s video - "
                        "for a Short, pass --hook-seconds with the length of the opening line")
    if start > 100.5:
        warnings.append(f"retention starts at {start:g}% - over 100 is rewatching as a Short loops")
    if pct_axis and not dur:
        warnings.append("percent axis with no --duration: cliffs cannot be given in seconds")
    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    drops.sort(reverse=True)
    cliffs = [{"from": round(a1, 2), "to": round(b1, 2), "lost": round(d, 2),
               "at_seconds": round(at(a1), 1) if timed else None}
              for _, a1, b1, d in drops[:5] if d > 0.8]
    mid = [rate for rate, x0, _, _ in drops if x0 > cutoff]
    slide = sum(mid) / len(mid) if mid else 0
    unit = "% of viewers per second" if not pct_axis else "% of viewers per 1% of runtime"
    said = {}
    if o.transcript and os.path.exists(o.transcript):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "yt-edit"))
        from deadair import load as load_cues
        cues = load_cues(o.transcript)
        for c in cliffs:
            if c["at_seconds"] is None: continue
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]
    out = {"points": len(rows), "axis": axis, "axis_reason": why, "duration": dur,
           "hook_seconds": hs, "start": start, "hook_leak": round(hook_leak, 2),
           "end": ys[-1], "cliffs": cliffs, "slide_per_unit": round(slide, 3), "slide_unit": unit,
           "said": said, "warnings": warnings}
    if o.json: print(json.dumps(out, indent=1)); return
    print(f"\n  {o.csv}   {len(rows)} points   {ys[0]:.1f}% -> {ys[-1]:.1f}%")
    print(f"  axis: {axis} ({why})\n")
    for w in warnings: print(f"  NOTE  {w}")
    if warnings: print()
    verdict = "healthy" if hook_leak < 25 else "leaking" if hook_leak < 40 else "severe"
    print(f"  HOOK LEAK   {hook_leak:.1f}% lost in the first {hs:g}s   [{verdict}]")
    print(f"              under 25 is healthy for this length. Fix the first line before anything else.\n")
    print("  CLIFFS      the moments people actually left")
    for c in cliffs:
        where = f"{c['at_seconds']:.0f}s" if c["at_seconds"] is not None else f"{c['from']}%"
        print(f"    -{c['lost']:5.1f}%  at {where:>8}" + (f"   \"{said.get(str(c['from']),'')}\"" if said else ""))
    if not cliffs: print("    none steeper than 0.8% - the loss is all slide, not moments")
    print(f"\n  SLIDE       {slide:.3f} {unit} across the middle")
    print( "              a flat slide is pacing, not content. Cut the middle, do not rewrite it.\n")

if __name__ == "__main__":
    main()
