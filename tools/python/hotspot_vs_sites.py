#!/usr/bin/env python3
"""hotspot_vs_sites.py - of the allocation sites a report names, how many C2 already removes.

    python3 tools/python/hotspot_vs_sites.py --elim build/out/hotspot/avrora.tsv \
        --objects build/out/param-hubs/avrora-false.objects.json --label avrora [--match hub]

--elim is tools/python/hotspot_elim.py output; --objects is tools/python/param_hubs.py --objects-out. For each
list in --objects (optionally only the lists whose name contains --match), counts the sites:
  compiled     the site's method was parsed by C2 at least once (root or inlined)
  EA removed   an eliminate_allocation event names the site
  concat       a replace_string_concat event names the site (the builder's `new`)
  either       at least one of the two
Sites join on (Soot method signature, bci). A removal counted here happened in at least one
compilation; it is not a claim that the site never allocates (see hotspot_elim.py).
"""
import argparse
import json
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elim", required=True)
    ap.add_argument("--objects", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--match", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    parsed, ev = set(), defaultdict(set)
    with open(a.elim, encoding="utf-8") as fh:
        for line in fh:
            e, _ty, sig, bci, _n, _inl = line.rstrip("\n").split("\t")
            if e == "parsed":
                parsed.add(sig)
            else:
                ev[(sig, int(bci))].add(e)
    with open(a.objects, encoding="utf-8") as fh:
        lists = json.load(fh)

    out = {}
    print("== %s  (C2 parsed %d methods; %d sites with a removal event)"
          % (a.label, len(parsed), len(ev)))
    print("   %-78s %6s %8s %8s %8s %8s" % ("list", "sites", "compiled", "EA", "concat", "either"))
    for name, sites in lists.items():
        if a.match and a.match not in name:
            continue
        keys = [(m, int(b)) for m, b in sites]
        comp = sum(1 for k in keys if k[0] in parsed)
        ea = sum(1 for k in keys if "eliminate_allocation" in ev.get(k, ()))
        cc = sum(1 for k in keys if "replace_string_concat" in ev.get(k, ()))
        ei = sum(1 for k in keys if ev.get(k))
        out[name] = dict(sites=len(keys), compiled=comp, ea=ea, concat=cc, either=ei)
        print("   %-78s %6d %8d %8d %8d %8d" % (name[:78], len(keys), comp, ea, cc, ei))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"label": a.label, "lists": out}, fh, indent=2)


if __name__ == "__main__":
    main()
