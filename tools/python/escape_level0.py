#!/usr/bin/env python3
"""escape_level0.py - what the sites are that Stava calls Escape and the up-walk puts at level 0.

    python3 tools/python/escape_level0.py --sites build/out/capture-level/avrora-false-cap50.sites.json \
        --alloc-dir /tmp/rv/p6info/avrora-false --objects build/out/param-hubs/avrora-false.objects.json

Those sites escape in Stava only through a resolution the walk does not repeat: Stava resolves a
parameter against every call site of its method at once, the walk returns to the call site it
came from. Prints them by allocated type, and how many are sites of each top parameter hub.
"""
import argparse
import glob
import json
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", required=True)
    ap.add_argument("--alloc-dir", required=True)
    ap.add_argument("--objects", default=None)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    rows = json.load(open(a.sites, encoding="utf-8"))
    e0 = {(m, b) for m, b, v, l in rows if v == "Escape" and l == "0"}
    esc = sum(1 for _m, _b, v, _l in rows if v == "Escape")
    types = {}
    f = glob.glob(a.alloc_dir + "/*.alloc")[0]
    sets = {}
    for line in open(f[:-len(".alloc")] + ".allocsets", encoding="utf-8"):
        sid, _, body = line.rstrip("\n").partition("\t")
        sets[sid] = body
    for line in open(f, encoding="utf-8"):
        m, b, t, k, s = line.rstrip("\n").split("\t")
        if k == "NEW" and t == "internal":
            types[(m, int(b))] = sets.get(s, "?|?|?").split(";")[0].rsplit("|", 1)[-1]
    tc = Counter(types.get(k, "?") for k in e0)
    print("== %s: %d of %d escaping sites at level 0 (%.1f %%)"
          % (a.label, len(e0), esc, 100.0 * len(e0) / max(1, esc)))
    for t, c in tc.most_common(8):
        print("      %-50s %5d" % (t, c))
    if a.objects:
        lists = json.load(open(a.objects, encoding="utf-8"))
        hub = [(n, {(m, int(b)) for m, b in l}) for n, l in lists.items() if n.startswith("hub ")]
        in_hub = set()
        for n, s in hub:
            hit = len(s & e0)
            in_hub |= s & e0
            if hit:
                print("      in %-70s %5d of %d" % (n[4:74], hit, len(s)))
        print("      in any top-15 hub: %d; in none: %d" % (len(in_hub), len(e0 - in_hub)))


if __name__ == "__main__":
    main()
