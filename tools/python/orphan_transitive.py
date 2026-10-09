#!/usr/bin/env python3
"""orphan_transitive.py - nodes whose reason claims a successor they do not have.

TRANSITIVE_SUCCESSOR and PARAM_ESCAPES_VIA_SUCCESSOR both mean "something downstream escaped".
A node carrying either with ZERO out-edges is self-contradictory, and is direct evidence of
either X-A2 (the edge was destroyed by purge() after the reason was recorded) or X-A4 (the
reason was stamped onto it from a component sibling).

Unlike the 4/50 blob heuristics in benchmark_scale and escape_blast, this DETECTS damage
rather than thresholding for it: the contradiction is checkable per node.
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons

PROP = {"TRANSITIVE_SUCCESSOR", "PARAM_ESCAPES_VIA_SUCCESSOR"}


def main():
    d, label = sys.argv[1], sys.argv[2]
    nodes, _he, dep, _f = build(d, [""], read_reasons(find_reasons_file(d, None), mode="raw"))
    out = defaultdict(set)
    for s, t, _p in dep:
        out[s].add(t)

    per_type, tot = Counter(), Counter()
    for i, n in nodes.items():
        if set(n.get("escapeReasons") or ()) & PROP:
            tot[n["objType"]] += 1
            if not out.get(i):
                per_type[n["objType"]] += 1

    print("== %s" % label)
    print("   nodes claiming a successor reason, but having NO out-edge")
    print("   %-12s %10s %10s %8s" % ("objType", "claiming", "orphaned", "share"))
    for t in sorted(tot, key=lambda k: -tot[k]):
        print("   %-12s %10d %10d %7.1f%%"
              % (t, tot[t], per_type[t], 100.0 * per_type[t] / max(1, tot[t])))
    print("   %-12s %10d %10d %7.1f%%"
          % ("TOTAL", sum(tot.values()), sum(per_type.values()),
             100.0 * sum(per_type.values()) / max(1, sum(tot.values()))))


if __name__ == "__main__":
    main()
