#!/usr/bin/env python3
"""p6_summary.py - one table per question from the patch-0006 analysis outputs in build/out/.

    python3 tools/python/p6_summary.py [build/out]

Reads alloc-unit/*.json (alloc_unit.py), frame-depth/*.json (frame_depth.py),
capture-level/*-cap{2,50}.json (capture_level.py) and hotspot/*-vs.json (hotspot_vs_sites.py).
"""
import glob
import json
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                           "..", "build", "out")
RUNS = ["avrora-false", "avrora-true", "xalan-false", "luindex-false", "fop-false", "h2-false",
        "pmd-false"]


def load(sub, name):
    p = os.path.join(OUT, sub, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def pct(a, b):
    return "%.1f" % (100.0 * a / b) if b else "-"


print("== F4: nodes -> application allocation sites; single-reason share of escaping, by rule")
print("%-14s %6s %6s %6s %8s %8s | %6s %6s %6s %6s" % ("run", "nodes", "sites", "ratio", "aliases",
                                                   "outside", "nodes", "own", "single", "union"))
for r in RUNS:
    j = load("alloc-unit", r + ".json")
    if not j:
        continue
    mb = j["multBefore"]
    eb = sum(v for k, v in mb.items() if k != "0")
    rules = j["rules"]
    print("%-14s %6d %6d %6.2f %8d %8d | %6s %6s %6s %6s" % (
        r, j["nodes"], j["sites"], j["nodes"] / j["sites"], j["stats"].get("alias", 0),
        sum(j["outside"].values()), pct(mb.get("1", 0), eb),
        "%.1f" % rules["own node only"]["single"], "%.1f" % rules["unambiguous aliases"]["single"],
        "%.1f" % rules["union"]["single"]))

print("\n== F4: alias ambiguity (aliases naming >1 / >20 application sites) and NoEscape conflicts")
for r in RUNS:
    j = load("alloc-unit", r + ".json")
    if not j:
        continue
    h = {int(k): v for k, v in j["stats"]["alias set size histogram"].items()}
    tot = sum(h.values())
    print("%-14s aliases %5d  >1: %5d (%s %%)  >20: %4d  conflicts %d  outside escaping %d of %d" % (
        r, tot, tot - h.get(1, 0), pct(tot - h.get(1, 0), tot), h.get(21, 0),
        j["stats"].get("conflict: escaping alias of a NoEscape site (not applied)", 0),
        sum(j["outsideEscaping"].values()), sum(j["outside"].values())))

print("\n== frames down (frame_depth.py), NoEscape sites: max depth histogram, then beyond constructors")
for r in RUNS:
    j = load("frame-depth", r + ".json")
    if not j:
        continue
    v = j["byVerdict"].get("NoEscape")
    if not v:
        continue
    for m in ("max", "min", "noinit"):
        h = v["hist"][m]
        print("%-14s %-6s n=%4d  %s" % (r if m == "max" else "", m, v["sites"],
                                         " ".join("%s:%s" % (k, h[k]) for k in sorted(h, key=int) if h[k])))

print("\n== frames up (capture_level.py): levels over all application allocation sites")
for r in RUNS:
    for cap in (2, 50):
        j = load("capture-level", "%s-cap%d.json" % (r, cap))
        if not j:
            continue
        lv = j["levels"]
        n = j["sites"]
        nums = sorted((k for k in lv if not k.startswith("heap")), key=int)
        print("%-14s cap %-2d n=%4d  %s | %s" % (
            r, cap, n, " ".join("%s:%d" % (k, lv[k]) for k in nums),
            " ".join("%s:%d" % (k[6:], v) for k, v in sorted(lv.items()) if k.startswith("heap"))))
        print("%14s cross %s" % ("", j["cross"]))

print("\n== frames up, hoist candidates (param_hubs, pessimistic) at cap 50")
for r in RUNS:
    j = load("capture-level", "%s-cap50.json" % r)
    if not j:
        continue
    for name, h in j["subsets"].items():
        if name.startswith("hoist candidates, pessimistic") or name.startswith("routed"):
            n = sum(h.values())
            nums = sorted((k for k in h if not k.startswith("heap")), key=int)
            print("%-14s %-32s n=%4d  %s | heap %d" % (
                r, name[:32], n, " ".join("%s:%d" % (k, h[k]) for k in nums),
                sum(v for k, v in h.items() if k.startswith("heap"))))

print("\n== HotSpot C2 vs the StringBuilder/StringBuffer hub and the hoist candidates")
for r in RUNS:
    j = load("hotspot", r + "-vs.json")
    if not j:
        continue
    for name, v in j["lists"].items():
        if "StringB" in name or name.startswith("hoist candidates, pessimistic"):
            print("%-14s %-60s sites %4d compiled %4d EA %3d concat %3d either %3d" % (
                r, name[:60], v["sites"], v["compiled"], v["ea"], v["concat"], v["either"]))
