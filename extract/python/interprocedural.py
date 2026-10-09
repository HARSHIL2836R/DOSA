#!/usr/bin/env python3
"""
interprocedural.py — graph.json (per-method) -> graph-interproc.json (one merged heap graph)

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
Stava keeps one PointsToGraph per method and object refs are method-local: <internal,0> in
makeBox and <internal,0> in main are different objects. Nothing in Stava merges points-to
graphs across methods - that is precisely the gap Clustering-Design 5 names and Meet 4
assigned ("Stava only does summary merging, not PTA merging").

This script RECONSTRUCTS what a fully interprocedural PTG would look like, by stitching the
per-method graphs together using the binding information that Stava's conditional values
already carry. It is a visualisation of an inferred graph, NOT a sound interprocedural
points-to analysis. Every figure built from it says so.

Specifically it does NOT: distinguish call sites (no context sensitivity), so bindings are
merged across all call sites of a method; model reflection, native methods or invokedynamic;
or do any fixpoint of its own. It reads what Stava already computed and joins it up.

THE THREE STITCHING RULES
-------------------------
1. RETURN aliasing.  A caller's `x = foo()` creates an `external` object in the caller. Both
   that external object and the object foo actually returns carry the SAME conditional value
   <foo,<returnValue,k>>. So: union every object that points at a given returnValue node.
   The result is one node standing for "the thing foo returns".

     M02: <external,3> and <external,20> in main, and <internal,0> in makeBox, all carry
     <<M02: Box makeBox()>,<returnValue,0>>. They collapse to one node - which is exactly
     the allocation-site merging that PTA-Task-List task 8 asks us to measure.

2. ARGUMENT binding.  An object O carrying <u,<parameter,i>,[T]> is passed as argument i to
   u. So (u, parameter i) binds to O. Bindings from all call sites are unioned, because we
   have no call-site sensitivity.

3. Parameter elimination.  A callee field edge such as fill's
   <parameter,0> --Box.item--> <parameter,1> is rewritten through those bindings into
   caller-level object edges, and the parameter nodes are then dropped. This is where the
   imprecision becomes visible: binding is a cross product, so one field edge in `fill`
   becomes an edge from every possible box to every possible item.

escapeStatus for a collapsed node is the join over its members (Escape wins, since
EscapeStatus is read as a disjunction). If members disagree, that is recorded in
"statusConflict" rather than being hidden.

USAGE
  python3 extract/python/interprocedural.py --graph build/out/M02-pye/graph.json \
      --out build/out/M02-pye/graph-interproc.json
"""

import argparse
import json


class Union:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # deterministic: smaller id becomes the root
        if rb < ra:
            ra, rb = rb, ra
        self.p[rb] = ra


def tarjan_scc(vertices, adj):
    index, low, on_stack, stack, result = {}, {}, set(), [], {}
    counter, scc_id = [0], [0]
    for root in vertices:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                on_stack.add(v)
            recursed = False
            succs = sorted(adj.get(v, []))
            for i in range(pi, len(succs)):
                w = succs[i]
                if w not in index:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if recursed:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    result[w] = scc_id[0]
                    if w == v:
                        break
                scc_id[0] += 1
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--definition", choices=["S", "C"], default="S")
    a = ap.parse_args()

    with open(a.graph, encoding="utf-8") as fh:
        g = json.load(fh)

    by_id = {n["id"]: n for n in g["nodes"]}
    objs = {n["id"] for n in g["nodes"] if n["kind"] == "object"}
    params = {n["id"] for n in g["nodes"] if n["kind"] == "param"}
    retvals = {n["id"] for n in g["nodes"]
               if n["kind"] == "param" and n.get("type") == "returnValue"}

    # ---- rule 1: RETURN aliasing -----------------------------------------------------
    uf = Union()
    for o in sorted(objs):
        uf.find(o)
    ret_members = {}
    for e in g["edges"]:
        if e["toNode"] in retvals and e["fromNode"] in objs:
            ret_members.setdefault(e["toNode"], []).append(e["fromNode"])
    for rv, members in sorted(ret_members.items()):
        members = sorted(members)
        for m in members[1:]:
            uf.union(members[0], m)

    # ---- rule 2: ARGUMENT binding ----------------------------------------------------
    binding = {}
    for e in g["edges"]:
        if e["provenance"] == "ARGUMENT" and e["toNode"] in params \
                and e["toNode"] not in retvals and e["fromNode"] in objs:
            binding.setdefault(e["toNode"], set()).add(uf.find(e["fromNode"]))

    # ---- choose a representative + label per alias class ------------------------------
    classes = {}
    for o in sorted(objs):
        classes.setdefault(uf.find(o), []).append(o)

    rep_node = {}
    for root, members in sorted(classes.items()):
        # prefer a real allocation site (an `internal` object with a known Java type)
        def rank(mid):
            n = by_id[mid]
            is_internal = str(n.get("sootNode", "")).startswith("<internal")
            known_type = n.get("type") not in (None, "external", "internal")
            return (0 if (is_internal and known_type) else 1, mid)

        best = sorted(members, key=rank)[0]
        src = by_id[best]
        statuses = sorted({by_id[m].get("escapeStatus") for m in members
                           if by_id[m].get("escapeStatus")})
        status = "Escape" if "Escape" in statuses else (
            statuses[0] if statuses else None)
        node = dict(
            id=root, kind="object", method=src.get("method"), bci=src.get("bci"),
            type=src.get("type"), isReal=None, label=src.get("label"),
            sootNode=src.get("sootNode"), escapeStatus=status,
            aliases=sorted(members),
            aliasCount=len(members),
            statusConflict=(len(statuses) > 1),
        )
        if len(members) > 1:
            node["label"] = "%s  (x%d)" % (src.get("label"), len(members))
        rep_node[root] = node

    # ---- rule 3: rewrite containment through the bindings, drop parameter nodes -------
    def resolve(nid):
        """A node id -> the set of merged object nodes it stands for."""
        if nid in objs:
            return {uf.find(nid)}
        if nid in binding:
            return set(binding[nid])
        return set()

    out_edges, dropped = [], 0
    for e in g["edges"]:
        if e["provenance"] != "CONTAINMENT" or e.get("derived"):
            continue
        srcs, dsts = resolve(e["fromNode"]), resolve(e["toNode"])
        if not srcs or not dsts:
            dropped += 1
            continue
        for s in sorted(srcs):
            for d in sorted(dsts):
                out_edges.append(dict(fromNode=s, toNode=d,
                                      fieldPath=e["fieldPath"],
                                      provenance="CONTAINMENT", derived=False,
                                      viaParameter=e["fromNode"] in params
                                      or e["toNode"] in params))

    # ---- sinks + verdict edges --------------------------------------------------------
    nodes = dict(rep_node)
    for sink in ("Escape", "NoEscape"):
        nodes["sink:" + sink] = dict(id="sink:" + sink, kind="sink", method=None,
                                     bci=None, type=sink, isReal=None, label=sink,
                                     escapeStatus=sink, equiEscapeSet=None)
    for n in list(rep_node.values()):
        if n["escapeStatus"] in ("Escape", "NoEscape"):
            out_edges.append(dict(fromNode=n["id"], toNode="sink:" + n["escapeStatus"],
                                  fieldPath=[], provenance="SINK", derived=False))

    # dedupe
    seen, uniq = set(), []
    for e in sorted(out_edges, key=lambda x: (x["fromNode"], x["toNode"],
                                              x["provenance"], str(x["fieldPath"]))):
        k = (e["fromNode"], e["toNode"], e["provenance"], tuple(e["fieldPath"]))
        if k not in seen:
            seen.add(k)
            uniq.append(e)

    # ---- definitions S and C on the MERGED graph --------------------------------------
    s_ids, s_key = {}, {}
    for n in sorted(rep_node.values(), key=lambda x: x["id"]):
        k = n.get("escapeStatus") or "unresolved"
        if k not in s_ids:
            s_ids[k] = len(s_ids)
        s_key[n["id"]] = s_ids[k]

    adj = {}
    for e in uniq:
        if e["provenance"] == "CONTAINMENT":
            adj.setdefault(e["fromNode"], []).append(e["toNode"])
    c_key = tarjan_scc(sorted(rep_node), adj)

    for n in nodes.values():
        if n["kind"] == "sink":
            n["equiEscapeSetS"] = n["equiEscapeSetC"] = n["equiEscapeSet"] = None
        else:
            n["equiEscapeSetS"] = s_key.get(n["id"])
            n["equiEscapeSetC"] = c_key.get(n["id"])
            n["equiEscapeSet"] = (n["equiEscapeSetS"] if a.definition == "S"
                                  else n["equiEscapeSetC"])

    meta = dict(g["meta"])
    meta["view"] = ("interprocedural (reconstructed): per-method PTGs stitched via "
                    "returnValue aliasing and parameter binding; parameter nodes "
                    "eliminated. NOT a sound interprocedural PTA - Stava merges summaries, "
                    "not points-to graphs.")
    meta["stitching"] = {
        "returnAliasClasses": {k: sorted(v) for k, v in sorted(ret_members.items())},
        "parameterBindings": {k: sorted(v) for k, v in sorted(binding.items())},
        "mergedNodes": {n["id"]: n["aliases"] for n in rep_node.values()
                        if n["aliasCount"] > 1},
        "containmentEdgesDroppedUnbound": dropped,
        "contextSensitivity": "none - bindings unioned across all call sites",
    }

    out = {"meta": meta,
           "nodes": sorted(nodes.values(), key=lambda x: x["id"]),
           "edges": uniq}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")

    o = [n for n in nodes.values() if n["kind"] == "object"]
    cont = [e for e in uniq if e["provenance"] == "CONTAINMENT"]
    print(a.out)
    print("  merged objects     : %d (from %d per-method objects)" % (len(o), len(objs)))
    print("  alias merges       : %s" % (
        ", ".join("%s <- %d" % (n["label"], n["aliasCount"])
                  for n in sorted(o, key=lambda x: x["id"]) if n["aliasCount"] > 1)
        or "none"))
    print("  containment edges  : %d" % len(cont))
    print("  NoEscape / Escape  : %d / %d" % (
        sum(1 for n in o if n["escapeStatus"] == "NoEscape"),
        sum(1 for n in o if n["escapeStatus"] == "Escape")))
    print("  sets under S       : %d" % len({n["equiEscapeSetS"] for n in o}))
    print("  sets under C       : %d" % len({n["equiEscapeSetC"] for n in o}))
    if dropped:
        print("  WARNING: %d containment edges dropped (unbound endpoint)" % dropped)


if __name__ == "__main__":
    main()
