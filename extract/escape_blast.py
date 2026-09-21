#!/usr/bin/env python3
"""
escape_blast.py - rank escape ROOT CAUSES by how many objects they cost.

WHY THIS IS NOT benchmark_scale.py's REASON TABLE
  benchmark_scale.py counts, for each EscapeReason, how many objects carry it. That number is
  wrong for prioritisation in two independent ways, both measured in Phase 11/12:

    1. Component-wide attribution. ReworkedResolver.resolve() calls SetComponent(component,
       Escape), so a reason that fired on ONE member of an SCC is stamped on ALL of them.
       pmd reports THREAD_REACHABLE_CLASS on 955 objects and has 0 outside the giant SCC.
    2. Propagation is counted like causation. TRANSITIVE_SUCCESSOR is the largest bucket in
       every benchmark and is not a cause - it says "something downstream escaped".

  This tool answers what those counts cannot: if you FIXED one thing, how many objects stop
  escaping.

THE GRAPH AND ITS DIRECTION  (verified empirically, not assumed)
  A summary entry `X = [<M, <parameter,k>, [T]>]` means "X escapes IF M's parameter k escapes".
  build() emits that as X -> (M, parameter, k). Edges point from an object TO the thing to
  blame, so the objects that escape BECAUSE of N are the ones that REACH N.

  Direction check on the unfiltered avrora run, over the 36,317 nodes whose reason set is
  purely {TRANSITIVE_SUCCESSOR, PARAM_ESCAPES_VIA_SUCCESSOR}:
      >=1 out-edge 88.2%   >=1 in-edge 27.5%
      >=1 out-edge to an unknown-status node 74.8%   >=1 in-edge from one 0.0%
  Targets are synthesised from conditional values and may carry no summary; sources are always
  real summary keys. That asymmetry is only possible in this direction.

WHAT A ROOT CAUSE IS HERE
  Condense the escaping subgraph into SCCs. A SINK SCC has no outgoing edge to another
  escaping SCC: there is nothing further to blame, so that is where the escape starts.

  AN EARLIER VERSION OF THIS FILE CLAIMED SCC GRANULARITY MADE THIS IMMUNE TO PROBLEM (1).
  IT DOES NOT, AND THE RUN DISPROVES IT. The resolver's component is over its own
  StandardObject graph; this graph is rebuilt from the .info summaries and is not the same
  relation, so a resolver component is generally NOT an SCC here. On avrora, 20,004 causes
  carry more than one root reason and 19,920 of those are SINGLETON SCCs - the extra reasons
  cannot have come from this condensation. 16,810 of them carry one identical four-reason set
  (ASSIGNED_TO_THIS_OR_PARAM, CONSTANT_OBJECT, MONITOR, STATIC_FIELD_LOAD): the stamped blob.

  So: the RANKING is structural - reachability over the dependency graph - and is unaffected.
  The `root reasons` COLUMN is not. For a cause inside a stamped component it is the
  component's union, not the reason that fired at that node. The by-reason table therefore
  reports twice, raw and net of stamped sets.

TWO BLAST RADII, AND ONLY THE SECOND IS A PROMISE
  gross      objects that reach this sink. Sums to far more than the program, because an object
             reaching three sinks is counted by all three.
  exclusive  objects that reach THIS sink AND NO OTHER. These actually become non-escaping if
             you fix this sink alone. This is the number to plan against.

POPULATION
  No objectType filter. benchmark_scale.py reports over internal+external only, which drops
  24-43% of nodes and silently zeroes EscapeReason.RETURNED (it can only land on
  <returnValue,0>). Here every node is counted and every table is split by objectType instead.

  --class-prefix is a REPORTING label, not a graph filter. The whole run is read so that
  reachability is complete; app vs library is a column. Filtering the graph would cut exactly
  the edges that carry app objects into library sinks, which is what we are looking for.
"""
import argparse, json, os, sys
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons, tarjan_scc

# Reasons describing propagation rather than a cause. Everything else is a root reason.
PROPAGATED = {"TRANSITIVE_SUCCESSOR", "PARAM_ESCAPES_VIA_SUCCESSOR"}
MANY = -1          # sentinel for "reaches more than one sink"
NONE = -2          # sentinel for "reaches no sink" (cannot happen for escaping nodes)


def is_app(cls, prefixes):
    return any(cls.startswith(p) for p in prefixes)


def topo_order(comp_ids, cadj):
    """Kahn over the condensation. Returns ids in an order where every successor precedes
    its predecessors (i.e. sinks first), which is the order the solo-sink fold needs."""
    indeg = Counter()
    for c in comp_ids:
        for d in cadj.get(c, ()):
            indeg[d] += 0
    for c in comp_ids:
        for d in cadj.get(c, ()):
            indeg[c] += 1          # count OUT-edges; we peel sinks first
    ready = [c for c in comp_ids if indeg[c] == 0]
    radj = defaultdict(list)
    for c in comp_ids:
        for d in cadj.get(c, ()):
            radj[d].append(c)
    out, seen = [], set()
    while ready:
        c = ready.pop()
        if c in seen:
            continue
        seen.add(c); out.append(c)
        for p in radj.get(c, ()):
            indeg[p] -= 1
            if indeg[p] == 0:
                ready.append(p)
    # the condensation is acyclic, so every id is reached; guard anyway
    for c in comp_ids:
        if c not in seen:
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+",
                    help="REPORTING label only - the whole run is read either way")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--include-heap-edges", action="store_true",
                    help="also fold PTG field edges in, REVERSED (contained -> container). "
                         "Off by default: the resolver propagates over summary dependency "
                         "edges only, and the containment cascade is already in the summaries")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    rpath = find_reasons_file(a.info_dir, None)
    if rpath is None:
        raise SystemExit("escape_blast needs a .reasons file; none in %s" % a.info_dir)
    # raw: this module walks propagation itself, over PROPAGATED
    reasons = read_reasons(rpath, mode="raw")

    # [""] == read every .info in the directory. Reachability must be complete.
    nodes, heap_edges, dep_edges, _files = build(a.info_dir, [""], reasons)

    def escaping(i):
        # escapeStatus is ",".join(sorted(state tokens)), and "Escape" is a SUBSTRING of
        # "NoEscape" - a plain `in` test on the string silently marks every non-escaping
        # node as escaping. Split and compare tokens.
        n = nodes.get(i)
        if not n:
            return False
        st = n.get("escapeStatus")
        if not st:
            return False
        return "Escape" in [t.strip() for t in st.split(",")]

    # DEPENDENCY EDGES ONLY, deliberately.
    #
    # ReworkedResolver builds `this.graph` from the summaries' conditional values, and that is
    # the relation it propagates escape over - PTG field edges are not in it. Two reasons not
    # to add them here:
    #
    #   1. Direction. parse_fields yields (owner, field, target), so a heap edge runs
    #      container -> contained. The escape implication runs the other way: if the CONTAINER
    #      escapes, the contents do. Adding them unreversed asserts "the container escapes if
    #      its field does", which is backwards, and reachability would then blame contents for
    #      their containers.
    #   2. Double counting. The container->contents cascade already happened intraprocedurally
    #      (PointsToGraph.cascadeEscape) before the summary was written, so its effect is
    #      already inside each method's summary and inside the recorded reasons. An object
    #      escaped by that cascade carries the cascading reason and so becomes its own cause
    #      here - which slightly over-attributes to the contained object rather than the
    #      container, and is stated rather than silently fixed.
    #
    # --include-heap-edges reverses them and folds them in, for anyone who wants to measure
    # the difference; it is off because it is not what the resolver does.
    adj = defaultdict(set)
    for s, d, p in dep_edges:
        adj[s].add(d)
    if a.include_heap_edges:
        for s, d, f, p in heap_edges:
            adj[d].add(s)

    # ---- population, with NO objectType filter -------------------------------------
    print("== %s" % a.label)
    print("   .reasons                : %s" % os.path.basename(rpath))
    print("\n   -- population by ObjectType (no filter; app = %s)"
          % ", ".join(a.class_prefix))
    print("   %-12s %9s %9s %9s %9s %9s"
          % ("objectType", "total", "app", "Escape", "NoEscape", "unresolved"))
    tot = Counter(); app_c = Counter(); esc_c = Counter(); noe_c = Counter(); unr_c = Counter()
    for i, n in nodes.items():
        t = n["objType"]
        tot[t] += 1
        if is_app(n["cls"], a.class_prefix):
            app_c[t] += 1
        st = n.get("escapeStatus")
        if st is None:
            unr_c[t] += 1
        elif "Escape" in st and "NoEscape" not in st:
            esc_c[t] += 1
        elif "NoEscape" in st:
            noe_c[t] += 1
    for t in sorted(tot, key=lambda k: -tot[k]):
        print("   %-12s %9d %9d %9d %9d %9d"
              % (t, tot[t], app_c[t], esc_c[t], noe_c[t], unr_c[t]))
    print("   %-12s %9d %9d %9d %9d %9d"
          % ("TOTAL", sum(tot.values()), sum(app_c.values()), sum(esc_c.values()),
             sum(noe_c.values()), sum(unr_c.values())))

    # ---- reason x objectType, no filter --------------------------------------------
    xt = defaultdict(Counter)
    for i, n in nodes.items():
        if not is_app(n["cls"], a.class_prefix):
            continue
        for r in (n.get("escapeReasons") or ()):
            xt[r][n["objType"]] += 1
    print("\n   -- reason x objectType, application only, NO filter")
    print("   %-30s %8s %8s %8s %8s %8s"
          % ("reason", "total", "internal", "external", "param", "returnV"))
    for r in sorted(xt, key=lambda k: -sum(xt[k].values())):
        c = xt[r]
        print("   %-30s %8d %8d %8d %8d %8d"
              % (r, sum(c.values()), c["internal"], c["external"],
                 c["parameter"], c["returnValue"]))

    # ---- escaping subgraph ----------------------------------------------------------
    # V = every escaping node, plus every unresolved node an escaping node points at. Those
    # unresolved ones are the library boundary: the analysis blamed something it never
    # summarised, and they must be able to appear as causes or the ranking would hide them.
    V = {i for i in nodes if escaping(i)}
    boundary = set()
    for u in list(V):
        for v in adj.get(u, ()):
            if v in nodes and not escaping(v) and nodes[v].get("escapeStatus") is None:
                boundary.add(v)
    V |= boundary
    sub = {u: sorted(v for v in adj.get(u, ()) if v in V) for u in V}

    order = sorted(V)
    comp = tarjan_scc(order, sub)
    members = defaultdict(list)
    for i, c in comp.items():
        members[c].append(i)

    cadj = defaultdict(set)
    for u in V:
        for v in sub[u]:
            if comp[u] != comp[v]:
                cadj[comp[u]].add(comp[v])

    # A component is a CAUSE if its reason union holds anything that is not propagation,
    # or if it is a boundary node (the analysis blamed an unsummarised callee).
    def creasons(c):
        s = set()
        for i in members[c]:
            s.update(nodes[i].get("escapeReasons") or ())
        return s

    causes, cause_reasons = set(), {}
    for c in members:
        rs = creasons(c)
        root = rs - PROPAGATED
        if all(i in boundary for i in members[c]):
            causes.add(c); cause_reasons[c] = rs or {"UNSUMMARISED_CALLEE"}
        elif root:
            causes.add(c); cause_reasons[c] = root

    sinks = {c for c in members if not cadj.get(c)}
    print("\n   -- escaping subgraph")
    print("   nodes                   : %d (of which %d boundary/unresolved)"
          % (len(V), len(boundary)))
    print("   SCCs                    : %d" % len(members))
    print("   non-singleton SCCs      : %d" % sum(1 for c in members if len(members[c]) > 1))
    print("   largest SCC             : %d nodes" % max(len(m) for m in members.values()))
    print("   sink SCCs               : %d" % len(sinks))
    print("   cause SCCs              : %d" % len(causes))
    print("   sinks that are NOT causes: %d   <- escaping with nothing to blame"
          % len(sinks - causes))

    # ---- fold the cause set up the condensation ------------------------------------
    # solo[c] = the unique cause c depends on, or MANY, or NONE. Successors first.
    solo = {}
    for c in topo_order(list(members), cadj):
        acc = NONE
        if c in causes:
            acc = c
        for d in cadj.get(c, ()):
            s = solo.get(d, NONE)
            if s == NONE:
                continue
            if acc == NONE:
                acc = s
            elif acc != s:
                acc = MANY
            if acc == MANY:
                break
        solo[c] = acc

    gross, exclusive = Counter(), Counter()
    nocause = 0
    for c, ms in members.items():
        w = len(ms)
        if solo[c] == NONE:
            nocause += w
        elif solo[c] != MANY:
            exclusive[solo[c]] += w
    # `exclusive` above is exact and O(V+E). `gross` needs a reverse reachability per cause,
    # which is O(V*E) if done for every one, so it is computed ON DEMAND for a shortlist only
    # and every printed table says so. Ranking is by `exclusive`, the number that is a promise.
    radj = defaultdict(list)
    for c in members:
        for d in cadj.get(c, ()):
            radj[d].append(c)

    gross_app = {}

    def _reach(c):
        seen, stack = {c}, [c]
        while stack:
            x = stack.pop()
            for p in radj.get(x, ()):
                if p not in seen:
                    seen.add(p); stack.append(p)
        return seen

    def gross_of(c):
        if c not in gross:
            seen = _reach(c)
            gross[c] = sum(len(members[x]) for x in seen)
            # The app-weighted radius is the one to plan against: how many of YOUR objects
            # this cause costs. The unweighted one is dominated by JDK nodes in every run.
            gross_app[c] = sum(1 for x in seen for i in members[x]
                               if is_app(nodes[i]["cls"], a.class_prefix))
        return gross[c]

    def gross_app_of(c):
        gross_of(c)
        return gross_app[c]

    print("   escaping nodes with NO cause: %d   <- reason-coverage gap" % nocause)

    # ---- describe a cause ------------------------------------------------------------
    def describe(c):
        ms = members[c]
        if len(ms) == 1:
            n = nodes[ms[0]]
            return "%s@%s.%s:%s" % (n["objType"], n["cls"].split(".")[-1],
                                    n["mname"], n["bci"])
        meths = {nodes[i]["method"] for i in ms}
        return "SCC of %d nodes in %d methods" % (len(ms), len(meths))

    def cause_is_app(c):
        return any(is_app(nodes[i]["cls"], a.class_prefix) for i in members[c])

    ranked = sorted(causes, key=lambda c: -exclusive.get(c, 0))
    short = ranked[:a.top]
    print("\n   -- ROOT CAUSES ranked by EXCLUSIVE blast radius")
    print("      exclusive = objects that reach this cause AND NO OTHER; fixing it alone")
    print("      frees exactly these. gross = all objects that reach it (overlapping).")
    print("   %9s %9s  %-42s %s" % ("exclusive", "gross", "cause", "root reasons"))
    for c in short:
        print("   %9d %9d  %-42s %s"
              % (exclusive.get(c, 0), gross_of(c), describe(c)[:42],
                 ",".join(sorted(cause_reasons[c]))[:60]))

    # aggregate the same thing by reason, so "which reason is most pressing" has an answer.
    # A root-reason SET that is both large and repeated across many causes is the resolver's
    # component union stamped onto each member, not k independent facts - same detection rule
    # as benchmark_scale's blob correction, applied here to cause reason-sets.
    STAMP_MIN_REASONS, STAMP_MIN_CAUSES = 3, 50
    setfreq = Counter(tuple(sorted(cause_reasons[c])) for c in causes)
    stamped = {k for k, n in setfreq.items()
               if len(k) >= STAMP_MIN_REASONS and n >= STAMP_MIN_CAUSES}
    by_reason_excl, by_reason_n = Counter(), Counter()
    by_reason_excl_net, by_reason_n_net = Counter(), Counter()
    n_stamped = 0
    for c in causes:
        key = tuple(sorted(cause_reasons[c]))
        is_stamped = key in stamped
        n_stamped += is_stamped
        for r in cause_reasons[c]:
            by_reason_excl[r] += exclusive.get(c, 0)
            by_reason_n[r] += 1
            if not is_stamped:
                by_reason_excl_net[r] += exclusive.get(c, 0)
                by_reason_n_net[r] += 1

    print("\n   -- stamped reason sets (component unions, not independent facts)")
    print("   distinct stamped sets   : %d" % len(stamped))
    print("   causes carrying one     : %d of %d (%.1f%%)"
          % (n_stamped, len(causes), 100.0 * n_stamped / max(1, len(causes))))
    for k in sorted(stamped, key=lambda k: -setfreq[k])[:4]:
        print("     %6d causes  %s" % (setfreq[k], ", ".join(k)))

    print("\n   -- most pressing REASONS, by exclusive objects freed")
    print("      raw = every cause credited to all of its root reasons.")
    print("      net = the same, excluding causes whose reason set is a stamped component")
    print("            union. net is the column to quote.")
    print("   %-30s %10s %10s %10s %10s"
          % ("reason", "objects", "causes", "netObjects", "netCauses"))
    for r in sorted(by_reason_excl, key=lambda k: -by_reason_excl_net[k]):
        print("   %-30s %10d %10d %10d %10d"
              % (r, by_reason_excl[r], by_reason_n[r],
                 by_reason_excl_net[r], by_reason_n_net[r]))

    # ---- leverage by cause type -------------------------------------------------------
    # `exclusive` is exact for every cause and costs nothing extra, so this is the whole
    # distribution rather than the head of a ranked list. It is the evidence for the claim
    # that no single fix site has much leverage; a ranked top-N cannot support that claim
    # because the tail is where a counterexample would hide.
    esc_total = len(V)
    print("\n   -- leverage by cause ObjectType (exact, all causes, no shortlist)")
    print("   %-12s %8s %10s %9s %9s %9s %9s"
          % ("objType", "causes", "sumExcl", "maxExcl", "excl=0", "excl>=10", "excl>=100"))
    by_t = defaultdict(list)
    for c in causes:
        by_t[nodes[sorted(members[c])[0]]["objType"]].append(exclusive.get(c, 0))
    for t in sorted(by_t, key=lambda k: -sum(by_t[k])):
        v = by_t[t]
        print("   %-12s %8d %10d %9d %9d %9d %9d"
              % (t, len(v), sum(v), max(v), sum(1 for x in v if x == 0),
                 sum(1 for x in v if x >= 10), sum(1 for x in v if x >= 100)))
    allv = sorted((exclusive.get(c, 0) for c in causes), reverse=True)
    for k in (1, 10, 100, 1000):
        if k <= len(allv):
            print("   top %-5d causes free %8d of %d escaping nodes (%.2f%%)"
                  % (k, sum(allv[:k]), esc_total,
                     100.0 * sum(allv[:k]) / max(1, esc_total)))

    # ---- the parameter question -------------------------------------------------------
    # "if a param is marked escaping, how many objects escape due to that same param"
    pcomps = {}
    for c, ms in members.items():
        if any(nodes[i]["objType"] == "parameter" for i in ms):
            pcomps[c] = ms
    # shortlist by in-degree so gross_of is called a bounded number of times
    cand = sorted(pcomps, key=lambda c: -len(radj.get(c, ())))[:400]
    prows = []
    for c in cand:
        pn = [nodes[i] for i in members[c] if nodes[i]["objType"] == "parameter"]
        rep = nodes[sorted(members[c])[0]]
        prows.append({
            "objType": rep["objType"], "method": rep["method"], "bci": rep["bci"],
            "cause": c in causes,
            "gross": gross_of(c),
            "exclusive": exclusive.get(c, 0),
            "label": describe(c),
            "app": cause_is_app(c),
            "params": sorted({"%s#%s" % (n["method"], n["bci"]) for n in pn})[:4],
            "reasons": sorted(creasons(c)),
        })
    prows.sort(key=lambda r: -r["gross"])
    print("\n   -- ESCAPING PARAMETERS by blast radius (top %d of %d parameter SCCs by"
          % (min(a.top, len(prows)), len(pcomps)))
    print("      in-degree; gross computed for the %d best only)" % len(cand))
    print("   %9s %9s %4s  %-40s %s" % ("gross", "exclusive", "app", "parameter", "reasons"))
    for r in prows[:a.top]:
        print("   %9d %9d %4s  %-40s %s"
              % (r["gross"], r["exclusive"], "yes" if r["app"] else "-",
                 (r["params"][0] if r["params"] else r["label"])[-40:],
                 ",".join(r["reasons"])[:44]))

    # ---- the same two rankings, restricted to the application ----------------------
    # The global tables above are dominated by JDK causes (String.equals, ArrayList.add),
    # which is a true fact about where app objects go but is not something the user can fix.
    app_causes = [c for c in causes if cause_is_app(c)]
    app_ranked = sorted(app_causes, key=lambda c: -exclusive.get(c, 0))[:a.top]
    print("\n   -- APPLICATION root causes, ranked by exclusive blast radius")
    print("   %9s %9s %9s  %-38s %s"
          % ("exclusive", "grossApp", "gross", "cause", "root reasons"))
    for c in app_ranked:
        print("   %9d %9d %9d  %-38s %s"
              % (exclusive.get(c, 0), gross_app_of(c), gross_of(c), describe(c)[:38],
                 ",".join(sorted(cause_reasons[c]))[:44]))

    app_p = [c for c in pcomps if cause_is_app(c)]
    app_p = sorted(app_p, key=lambda c: -len(radj.get(c, ())))[:300]
    app_prows = sorted(({"gross": gross_of(c), "grossApp": gross_app_of(c),
                         "exclusive": exclusive.get(c, 0), "label": describe(c),
                         "cause": c in causes,
                         "objType": nodes[sorted(members[c])[0]]["objType"],
                         "method": nodes[sorted(members[c])[0]]["method"],
                         "bci": nodes[sorted(members[c])[0]]["bci"],
                         "params": sorted({"%s#%s" % (nodes[i]["method"], nodes[i]["bci"])
                                           for i in members[c]
                                           if nodes[i]["objType"] == "parameter"})[:2],
                         "reasons": sorted(creasons(c))}
                        for c in app_p), key=lambda r: -r["grossApp"])
    print("\n   -- APPLICATION escaping parameters, by app-weighted blast radius")
    print("      grossApp = application objects that escape because this parameter does")
    print("   %9s %9s %9s  %s" % ("grossApp", "gross", "exclusive", "parameter"))
    for r in app_prows[:a.top]:
        print("   %9d %9d %9d  %s"
              % (r["grossApp"], r["gross"], r["exclusive"],
                 (r["params"][0] if r["params"] else r["label"])[:78]))

    out = {
        "meta": {"label": a.label, "reasons": os.path.basename(rpath),
                 "appPrefixes": a.class_prefix,
                 "population": "ALL ObjectTypes; no internal/external filter",
                 "grossNote": "gross computed on demand for a shortlist; rank is by exclusive"},
        "causes": [{"id": c, "label": describe(c), "app": cause_is_app(c),
                    "members": len(members[c]), "sink": c in sinks,
                    "objType": nodes[sorted(members[c])[0]]["objType"],
                    "method": nodes[sorted(members[c])[0]]["method"],
                    "bci": nodes[sorted(members[c])[0]]["bci"],
                    "exclusive": exclusive.get(c, 0), "gross": gross.get(c),
                    "reasons": sorted(cause_reasons[c])} for c in ranked],
        "params": prows,
        "appCauses": [{"id": c, "label": describe(c), "members": len(members[c]),
                       "objType": nodes[sorted(members[c])[0]]["objType"],
                       "method": nodes[sorted(members[c])[0]]["method"],
                       "bci": nodes[sorted(members[c])[0]]["bci"],
                       "exclusive": exclusive.get(c, 0), "gross": gross.get(c),
                       "grossApp": gross_app.get(c),
                       "reasons": sorted(cause_reasons[c])} for c in app_ranked],
        "appParams": app_prows,
        "leverage": {"escapingNodes": len(V),
                     "byType": {t: {"causes": len(v), "sumExclusive": sum(v),
                                    "maxExclusive": max(v),
                                    "zero": sum(1 for x in v if x == 0)}
                                for t, v in by_t.items()},
                     "topKFreed": {str(k): sum(allv[:k])
                                   for k in (1, 10, 100, 1000) if k <= len(allv)}},
        "stampedSets": [{"set": list(k), "causes": setfreq[k]}
                        for k in sorted(stamped, key=lambda k: -setfreq[k])],
        "byReason": [{"reason": r, "objects": by_reason_excl[r], "causes": by_reason_n[r],
                      "netObjects": by_reason_excl_net[r], "netCauses": by_reason_n_net[r]}
                     for r in sorted(by_reason_excl, key=lambda k: -by_reason_excl[k])],
        "integrity": {"escapingNodes": len(V), "boundaryNodes": len(boundary),
                      "sccs": len(members), "sinks": len(sinks), "causes": len(causes),
                      "sinksNotCauses": len(sinks - causes), "escapingWithNoCause": nocause},
    }
    with open(os.path.join(a.out_dir, "escape-blast.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print("\n   wrote %s" % os.path.join(a.out_dir, "escape-blast.json"))


if __name__ == "__main__":
    main()
