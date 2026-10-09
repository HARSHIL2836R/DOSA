#!/usr/bin/env python3
"""
population_split.py - per-ObjectType escape rates, application classes only.

The question X-D1 turns on: what is the denominator for "how many objects escape?"

benchmark_scale currently answers `internal + external`. This prints every ObjectType
separately so the choice can be made on numbers instead of convention. Nothing here filters
by type; --class-prefix is applied to the declaring class, exactly as the reported figures do.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons

TYPES = ("internal", "external", "parameter", "returnValue", "argument")


def main():
    info_dir, label = sys.argv[1], sys.argv[2]
    prefixes = sys.argv[3:]
    rp = find_reasons_file(info_dir, None)
    reasons = read_reasons(rp) if rp else None
    nodes, _he, _de, _f = build(info_dir, [""], reasons)

    tot, esc, noe, unr = Counter(), Counter(), Counter(), Counter()
    for n in nodes.values():
        if not any(n["cls"].startswith(p) for p in prefixes):
            continue
        t = n["objType"]
        tot[t] += 1
        st = n.get("escapeStatus")
        if st is None:
            unr[t] += 1
            continue
        toks = [x.strip() for x in st.split(",")]
        if "Escape" in toks:
            esc[t] += 1
        elif "NoEscape" in toks:
            noe[t] += 1
        else:
            unr[t] += 1

    print("== %s   (application only: %s)" % (label, ", ".join(prefixes)))
    print("   %-12s %8s %8s %8s %8s   %s"
          % ("objectType", "total", "Escape", "NoEscape", "unres", "NoEscape share"))
    for t in TYPES:
        if not tot[t]:
            continue
        d = esc[t] + noe[t]
        share = "%.2f%%" % (100.0 * noe[t] / d) if d else "-"
        print("   %-12s %8d %8d %8d %8d   %s"
              % (t, tot[t], esc[t], noe[t], unr[t], share))
    ie_t = tot["internal"] + tot["external"]
    ie_n = noe["internal"] + noe["external"]
    ie_d = ie_n + esc["internal"] + esc["external"]
    all_d = sum(esc.values()) + sum(noe.values())
    print("   %-12s %8d %8d %8d %8d   %s"
          % ("int+ext (X-D1)", ie_t, esc["internal"] + esc["external"], ie_n, 0,
             "%.2f%%" % (100.0 * ie_n / ie_d) if ie_d else "-"))
    print("   %-12s %8d %8d %8d %8d   %s"
          % ("ALL TYPES", sum(tot.values()), sum(esc.values()), sum(noe.values()),
             sum(unr.values()),
             "%.2f%%" % (100.0 * sum(noe.values()) / all_d) if all_d else "-"))


if __name__ == "__main__":
    main()
