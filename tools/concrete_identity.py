#!/usr/bin/env python3
"""concrete_identity.py - can views be merged into concrete objects, and at what cost?

THE MODEL BEING TESTED
  A concrete heap object is denoted, per method, by one of:
      <internal,bci>   allocated here
      <parameter,k>    passed in here
      <external,bci>   obtained here from a call result or field load
  and <returnValue,0> is NOT an object at all - it is the method's return slot, a marker.

  Merging those views needs the dependency edges, whose direction is "X escapes if Y escapes":

      caller C passing an object to M   ->  C:<obj> -> M:<parameter,k>
      callee M returning an object      ->  M:<obj> -> M:<returnValue,0>
      caller C using the call result    ->  C:<external,j> -> M:<returnValue,0>

  So a <parameter,k> with in-edges is a VIEW of the caller objects pointing at it, and a
  <returnValue,0> is a JOIN POINT: the callee's object and the caller's handle both point at
  it, which is what lets "returned" be pushed onto the concrete object.

WHAT THIS MEASURES
  1. parameter nodes with no in-edge      - un-mergeable, no caller in the analysed program
  2. returnValue nodes by which side points at them - whether the join actually closes
  3. internal nodes with an edge to a returnValue - how often "returned" is attributable
  4. internal nodes that escape with no out-edge at all - upper bound on the X-A2 casualties
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extract"))
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons


def main():
    d, label = sys.argv[1], sys.argv[2]
    reasons = read_reasons(find_reasons_file(d, None))
    nodes, _he, dep, _f = build(d, [""], reasons)

    out = defaultdict(set)
    inn = defaultdict(set)
    for s, t, _p in dep:
        out[s].add(t)
        inn[t].add(s)

    def ty(i):
        n = nodes.get(i)
        return n["objType"] if n else None

    def esc(i):
        n = nodes.get(i)
        st = n.get("escapeStatus") if n else None
        return bool(st) and "Escape" in [x.strip() for x in st.split(",")]

    print("== %s" % label)

    # 1. parameters
    params = [i for i, n in nodes.items() if n["objType"] == "parameter"]
    orphan = [i for i in params if not inn.get(i)]
    print("\n   parameter nodes                     : %d" % len(params))
    print("     mergeable (>=1 in-edge from a view): %d (%.1f%%)"
          % (len(params) - len(orphan),
             100.0 * (len(params) - len(orphan)) / max(1, len(params))))
    print("     ORPHAN (no caller in the program)  : %d (%.1f%%)"
          % (len(orphan), 100.0 * len(orphan) / max(1, len(params))))
    print("       ... of those, escaping           : %d" % sum(1 for i in orphan if esc(i)))

    # 2. returnValue join points
    rv = [i for i, n in nodes.items() if n["objType"] == "returnValue"]
    both = callee = caller = neither = 0
    for i in rv:
        m = nodes[i]["method"]
        srcs = inn.get(i, ())
        has_callee = any(ty(s) in ("internal", "external", "parameter")
                         and nodes[s]["method"] == m for s in srcs)
        has_caller = any(nodes[s]["method"] != m for s in srcs)
        if has_callee and has_caller:
            both += 1
        elif has_callee:
            callee += 1
        elif has_caller:
            caller += 1
        else:
            neither += 1
    print("\n   returnValue nodes                   : %d" % len(rv))
    print("     both sides point at it (join CLOSES): %d (%.1f%%)"
          % (both, 100.0 * both / max(1, len(rv))))
    print("     callee side only                   : %d" % callee)
    print("     caller side only (callee edge LOST): %d (%.1f%%)"
          % (caller, 100.0 * caller / max(1, len(rv))))
    print("     no in-edge at all                  : %d" % neither)

    # 3 & 4. internals
    internals = [i for i, n in nodes.items() if n["objType"] == "internal"]
    to_rv = [i for i in internals if any(ty(t) == "returnValue" for t in out.get(i, ()))]
    esc_int = [i for i in internals if esc(i)]
    noout = [i for i in esc_int if not out.get(i)]
    multi = [i for i in noout if len(nodes[i].get("escapeReasons") or []) >= 2]
    print("\n   internal nodes (allocation sites)   : %d" % len(internals))
    print("     with an edge to a returnValue      : %d (%.1f%%)  <- RETURN attributable"
          % (len(to_rv), 100.0 * len(to_rv) / max(1, len(internals))))
    print("     escaping                           : %d" % len(esc_int))
    print("       ... with NO out-edge at all      : %d (%.1f%% of escaping)"
          % (len(noout), 100.0 * len(noout) / max(1, len(esc_int))))
    print("       ... of those, >=2 direct reasons : %d  <- X-A2 casualty upper bound"
          % len(multi))
    rs = Counter()
    for i in noout:
        rs[tuple(sorted(nodes[i].get("escapeReasons") or []))] += 1
    print("     reason sets of the no-out-edge escapers (top 5):")
    for k, c in rs.most_common(5):
        print("       %6d  %s" % (c, ", ".join(k) or "(none)"))


if __name__ == "__main__":
    main()
