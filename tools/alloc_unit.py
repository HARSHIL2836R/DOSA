#!/usr/bin/env python3
"""alloc_unit.py - fix F4 measured: what the reason figures count before and after folding
Stava's objects onto allocation sites (extract/alloc_sites.py, patch 0006).

    python3 tools/alloc_unit.py --info-dir /tmp/rv/p6info/avrora-false --class-prefix avrora. \
        --label "avrora false" [--json out.json]

DIR holds the application .info files plus the run's .reasons, .via, .alloc and .allocsets.
Prints, in roots mode:
  - the population before (internal + external nodes) and after (application allocation sites)
  - where every non-site node went: alias of an application site, or outside by cause
  - how much the union of alias reasons adds, and how much of that rests on an alias that
    names several application sites (Spark imprecision is the only way that happens)
  - the reason multiplicity and the single-reason share, before and after
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from alloc_sites import find_alloc_file, fold, read_alloc  # noqa: E402
from benchmark_scale import build  # noqa: E402
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import SURRENDER, find_reasons_file, read_reasons  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    reasons = read_reasons(find_reasons_file(a.info_dir, None), mode="roots")
    nodes, _h, _d, files = build(a.info_dir, a.class_prefix, reasons)
    objs = {(n["method"], int(n["bci"]), n["objType"]): n for n in nodes.values()
            if n["kind"] == "object"}
    af = find_alloc_file(a.info_dir)
    if af is None:
        raise SystemExit("%s has no .alloc: not a patch-0006 run" % a.info_dir)
    alloc, nsets = read_alloc(af)

    def is_app(sig):
        q = parse_soot_sig(sig)
        return q is not None and any(q[0].startswith(x) for x in a.class_prefix)

    sites, stats, outside, outside_esc = fold(objs, alloc, is_app)
    rules = {}
    for name, amax in (("union", None), ("unambiguous aliases", 1), ("own node only", 0)):
        ss = fold(objs, alloc, is_app, amax)[0]
        m = Counter(len(x["reasons"]) for x in ss.values())
        e = sum(v for k, v in m.items() if k)
        rules[name] = dict(mult=dict(sorted(m.items())), escaping=e,
                           single=100.0 * m.get(1, 0) / e if e else None,
                           per=dict(Counter(r for x in ss.values() for r in x["reasons"])))

    kinds = Counter((k[2], alloc.get(k, ("MISSING",))[0]) for k in objs)
    esc_nodes = sum(1 for n in objs.values() if n.get("escapeReasons"))
    esc_sites = sum(1 for s in sites.values() if s["reasons"])

    def mult(sets):
        return Counter(len(x) for x in sets)

    before = mult(n.get("escapeReasons") or () for n in objs.values())
    after = mult(s["reasons"] for s in sites.values())
    after_own_only = mult(set(objs[s["node"]].get("escapeReasons") or ())
                          if s["escaping"] else () for s in sites.values())

    def single(m, tot):
        return "%.1f %%" % (100.0 * m.get(1, 0) / tot) if tot else "-"

    print("== %s  (%d .info files, %d distinct Spark site sets)" % (a.label, len(files), nsets))
    print("   before: %d nodes (internal %d, external %d), %d with a reason"
          % (len(objs), sum(1 for k in objs if k[2] == "internal"),
             sum(1 for k in objs if k[2] == "external"), esc_nodes))
    print("   node kinds (.alloc): %s" % dict(sorted(kinds.items())))
    print("   after : %d application allocation sites, %d with a reason; %.2f nodes per site"
          % (len(sites), esc_sites, len(objs) / max(1, len(sites))))
    print("   aliases folded onto sites: %d; alias sizes (application sites named, 21 = more): %s"
          % (stats.get("alias", 0), stats.get("alias set size histogram")))
    for k in ("alias target not a counted site",
              "conflict: escaping alias of a NoEscape site (not applied)",
              "sites gaining a reason only through aliases",
              "  of which some alias names several application sites"):
        print("      %-62s %6d" % (k, stats.get(k, 0)))
    no = sum(outside.values())
    print("   outside, not counted: %d nodes, %d escaping" % (no, sum(outside_esc.values())))
    for k, v in sorted(outside.items(), key=lambda kv: -kv[1]):
        print("      %-62s %6d  (escaping %d)" % (k, v, outside_esc.get(k, 0)))
    print("   multiplicity before: %s" % dict(sorted(before.items())))
    print("   multiplicity after : %s" % dict(sorted(after.items())))
    print("   (after, site's own node only, no alias union: %s)"
          % dict(sorted(after_own_only.items())))
    print("   single-reason share of escaping: before %s, after %s, after without the union %s"
          % (single(before, esc_nodes), single(after, esc_sites),
             single(after_own_only, sum(v for k, v in after_own_only.items() if k))))
    print("   by rule for alias reasons (multiplicity; single-reason share of escaping sites):")
    for name, r in rules.items():
        print("      %-22s %s  single %.1f %%" % (name, r["mult"], r["single"] or 0))
    per_after = Counter(r for s in sites.values() for r in s["reasons"])
    per_alias = Counter(r for s in sites.values() for r in s["aliasOnly"])
    print("   per reason, sites carrying it (of which only through an alias):")
    for r, c in per_after.most_common():
        print("      %-34s %6d  (%d)%s" % (r, c, per_alias[r], "  not a cause" if r in SURRENDER
                                         else ""))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"label": a.label, "nodes": len(objs), "sites": len(sites),
                       "escapingNodes": esc_nodes, "escapingSites": esc_sites,
                       "stats": stats, "outside": outside, "outsideEscaping": outside_esc,
                       "multBefore": dict(before), "multAfter": dict(after),
                       "multAfterNoUnion": dict(after_own_only),
                       "perReason": dict(per_after), "perReasonAliasOnly": dict(per_alias),
                       "rules": rules},
                      fh, indent=2)


if __name__ == "__main__":
    main()
