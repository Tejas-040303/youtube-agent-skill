#!/usr/bin/env python3
"""title.py - lint a YouTube title and thumbnail pairing before you publish it.

    python3 title.py --title "..." --thumb "AI RAN IT"
    python3 title.py titles.txt            # one per line, ranked
    python3 title.py --title "..." --json
    python3 title.py titles.txt --names "Simon Stevin,Galileo"   # names you know are in play

The pairing is the unit, not the title. A title that repeats the thumbnail text wastes half the
click surface, and that is the single most common mistake this checks for.

Length: YouTube truncates around 60 characters on desktop search and around 40 on a mobile home
feed. Both limits are reported because they are different failures - a desktop truncation loses the
tail, a mobile one can lose the subject.

Names: a capitalised word that does not start a sentence reads as a named thing. That cannot see a
name in first position ("Galileo never...") or anything in a Title Case title, where every word is
capitalised - so pass --names with the ones you know are in play and they are matched directly.
"""
import json, re, sys, os

DESKTOP, MOBILE, HARD = 60, 40, 100
VAGUE = {"amazing","incredible","insane","crazy","huge","massive","ultimate","best","powerful",
         "secret","revolutionary","mindblowing","epic","perfect","complete","everything"}
STOP = {"the","a","an","of","for","to","in","on","and","or","is","are","with","your","you","my","i",
        "this","that","it","how","what","why"}

def words(t): return re.findall(r"[a-z0-9']+", t.lower())

def named(t, known=()):
    """Named things in a title: the known names it contains, plus capitalised words that do not
    open a sentence. In Title Case every word is capitalised, so only the known names count."""
    found = [n for n in known if n and re.search(r"\b" + re.escape(n) + r"\b", t, re.I)]
    toks = re.findall(r"[A-Za-z][A-Za-z'’-]*|[.!?:]", t)
    content = [w for w in toks if w[0].isalpha() and w.lower() not in STOP]
    if len(content) >= 3 and sum(w[0].isupper() for w in content) / len(content) >= 0.8:
        return found
    opening = True
    for w in toks:
        if not w[0].isalpha():
            opening = True
            continue
        # all-caps is emphasis or an acronym, not a name; "I" is neither
        if not opening and w[0].isupper() and not w.isupper() and w.lower() not in STOP \
                and not any(w.lower() in n.lower().split() for n in found):
            found.append(w)
        opening = False
    return found

def check(title, thumb=None, known=()):
    t = title.strip()
    n = len(t)
    issues, good = [], []
    if n > HARD: issues.append(("length", f"{n} characters - YouTube's hard limit is {HARD}"))
    elif n > DESKTOP: issues.append(("length", f"{n} characters - desktop search cuts near {DESKTOP}"))
    else: good.append(f"{n} characters, inside the {DESKTOP}-character desktop cut")
    if n > MOBILE:
        head = t[:MOBILE].rsplit(" ", 1)[0]
        issues.append(("mobile", f'a mobile feed shows about "{head}..." - check the subject survives'))
    caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
    if len(caps) > 2: issues.append(("shouting", f"{len(caps)} all-caps words - two is the ceiling before it reads as spam"))
    elif caps: good.append(f"{len(caps)} all-caps word for emphasis")
    v = [w for w in words(t) if w in VAGUE]
    if v: issues.append(("vague", f"{', '.join(sorted(set(v)))} - swap for a number, a name or a date"))
    nums = re.findall(r"\d[\d,.]*%?", t)
    names = named(t, known)
    if nums: good.append(f"carries a concrete figure ({', '.join(nums[:3])})")
    if names: good.append(f"names {', '.join(names[:3])}")
    if not nums and not names:
        issues.append(("no-number", "no number, date or name - the most reliable single fix"))
    if t.endswith("?"): good.append("open question in the title")
    front = [w for w in words(t)[:3] if w not in STOP]
    if not front: issues.append(("front-load", "the first three words are all filler - move the subject forward"))
    if thumb:
        tw, hw = set(words(t)) - STOP, set(words(thumb)) - STOP
        shared = tw & hw
        if shared:
            issues.append(("duplicate", f"thumbnail repeats the title on {', '.join(sorted(shared))} - "
                                        "the thumbnail should say what the title does not"))
        else:
            good.append("thumbnail and title carry different words")
        if len(words(thumb)) > 4:
            issues.append(("thumb-length", f"{len(words(thumb))} words on the thumbnail - three is the ceiling at feed size"))
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "chars": n, "score": score, "issues": issues, "good": good, "names": names}

def show(r):
    print(f'\n  "{r["title"]}"')
    print(f"  {r['chars']} chars   score {r['score']}/100")
    for k, m in r["issues"]: print(f"    x  {k:<12} {m}")
    for m in r["good"]:      print(f"    ok              {m}")

def main():
    a = sys.argv[1:]
    as_json = "--json" in a; a = [x for x in a if x != "--json"]
    thumb = a[a.index("--thumb") + 1] if "--thumb" in a else None
    known = [n.strip() for n in a[a.index("--names") + 1].split(",")] if "--names" in a else []
    # the file is whichever argument is not a flag or a flag's value, wherever it sits
    values = {a.index(f) + 1 for f in ("--thumb", "--names", "--title") if f in a}
    files = [x for i, x in enumerate(a) if not x.startswith("--") and i not in values]
    if "--title" in a:
        rows = [check(a[a.index("--title") + 1], thumb, known)]
    elif files and os.path.exists(files[0]):
        rows = [check(l, thumb, known) for l in open(files[0], encoding="utf-8").read().splitlines() if l.strip()]
    else:
        print(__doc__); sys.exit(1)
    rows.sort(key=lambda r: -r["score"])
    if as_json: print(json.dumps(rows, indent=1)); return
    for r in rows: show(r)
    print()

if __name__ == "__main__":
    main()
