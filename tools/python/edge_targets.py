#!/usr/bin/env python3
"""edge_targets.py - which ObjectTypes can be the TARGET of a dependency edge.

Conditional values are built over interface objects only (getRetCV -> returnValue, caller
argument CVs -> parameter). If that is exhaustive then internal and external nodes have no
in-edges at all, and their exclusive blast radius is 1 by construction rather than by
measurement. Run it before quoting any per-type leverage number.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from collections import Counter
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons

d = sys.argv[1]
reasons = read_reasons(find_reasons_file(d, None))
nodes, _he, dep, _f = build(d, [""], reasons)
indeg = Counter()
for s, t, p in dep:
    n = nodes.get(t)
    if n:
        indeg[n["objType"]] += 1
tot = Counter(n["objType"] for n in nodes.values())
print("%-12s %10s %12s" % ("objType", "nodes", "in-edges"))
for t in sorted(tot, key=lambda k: -tot[k]):
    print("%-12s %10d %12d" % (t, tot[t], indeg.get(t, 0)))
