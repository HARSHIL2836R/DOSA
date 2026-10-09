#!/usr/bin/env python3
"""
benchmark_scale.py — measure and condense a benchmark-scale Stava run.

Why this is a separate tool from info_to_graph.py: PTA-Task-List task 15 is explicit that a
DaCapo heap graph will not render usefully as one picture, and that the CONDENSATION view is
the deliverable. So the benchmark path measures first and draws second, while the micro-corpus
path (info_to_graph.py, verified against eight hand-derivations) stays untouched.

It answers the M5 measurement of Clustering-Design 3.2 - "out-degree distribution of G_dep and
size distribution of its SCCs" - which is the gate that section says must run before a cluster
relation is chosen, and which has never been run.

FILTERING
  --class-prefix restricts to application classes by .info filename. .info files are
  partitioned one per declaring class, so this is exact. For the avrora run that means the 412
  `avrora.*.info` files out of 4289, which is the first application-only reading of that run;
  Benchmark-Setup-Log warns the headline 33,928 is JDK-dominated.

EDGE PROVENANCE AT BENCHMARK SCALE
  A `Fields:` entry is a points-to edge, but it can arise two ways, and they are not the same
  relation:

    STORE  a.f = b   -> containment: b is inside a.
    LOAD   a = b.f   -> b.f points at some object; LoadStmt creates an `external` object for
                        the loaded value and records the field edge.

  Discriminator used here: ObjectFactory.getObj types the created object `external` exactly
  when the RHS is an InvokeExpr, InstanceFieldRef or ArrayRef, and `internal` otherwise. So a
  field edge whose TARGET is `external` is tagged FIELD_LOAD and one whose target is
  `internal` is tagged CONTAINMENT.

  THIS IS AN INFERENCE, NOT A FACT STAVA RECORDS, AND IT IS NOT EXACT.
  Stava keeps ONE map -- PointsToGraph.fields -- and both `a.f = b` and `a = b.f` write into
  it; nothing in the PTG says which statement produced an edge. The rule above recovers the
  distinction from the target's type, and it fails in one direction: a genuine store of a
  previously-loaded value, `t = c.g; a.f = t`, reaches
  PointsToGraph.STRONG_makeField(lhs, f, rhs), which copies `vars.get(rhs)` wholesale -- so
  the stored object is `external` and the edge is mislabelled FIELD_LOAD.

  Earlier phases called this discriminator "exact". It was, under MarkStoreEscaping=true,
  because the store rule short-circuits at StoreStmt.java:38 and real stores never build field
  edges at all -- so every surviving edge really was a load or a constant store. Under
  MarkStoreEscaping=false, which is the configuration these runs now use, real stores do build
  field edges and the claim no longer holds. The size of the error is UNMEASURED.

  This matters because under MarkStoreEscaping=true (which is how the avrora run was made)
  StoreStmt short-circuits every `a.f = b` where b is a Local, so store-derived containment is
  almost entirely absent and nearly every field edge is a LOAD. Reporting those as
  CONTAINMENT would overstate the heap structure. The counts are printed separately so the
  reader can see which relation they are looking at.

ESCAPE REASONS  (added Phase 11)
  If <dirname>.reasons is present in --info-dir it is joined onto every node on
  (method signature, bci, objectType) and each node gains escapeReasons / reasonCount /
  realReasonCount / surrenderReasonCount. The join is additive: nothing that was already in
  graph-condensation.json, graph-drilldown.json or graph-full.json changes.

  A new graph-reasonsets.json is written alongside them. That is the reason-set CLUSTER view:
  one entry per DISTINCT reason set, not one per object, for the same reason the condensation
  exists - at avrora scale the per-object view is not a picture.

USAGE
  python3 extract/python/benchmark_scale.py --info-dir /tmp/avrora-info --class-prefix avrora. \\
      --label "avrora (DaCapo 9.12-MR1)" --jdk "Temurin 8u502-b07" \\
      --config "MarkStoreEscaping=true (upstream default)" \\
      --out-dir build/out/avrora
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from info_to_graph import (parse_info, split_passes, parse_objref, parse_cv,  # noqa: E402
                           parse_fields, split_map, strip_outer, soot_sig_parts,
                           tarjan_scc, find_reasons_file, read_reasons, reason_fields,
                           reason_set_clusters, REASON_ORDER, SURRENDER,
                           describe_reasons, own_of)


def build(info_dir, prefixes, reasons=None):
    nodes, heap_edges, dep_edges = {}, [], []
    files = sorted(f for f in os.listdir(info_dir)
                   if f.endswith(".info") and any(f.startswith(p) for p in prefixes))

    def nid(method, objtype, ref):
        return "%s|%s|%s" % (objtype, method, ref)

    for fn in files:
        blocks = parse_info(os.path.join(info_dir, fn))
        pre, post = split_passes(blocks)

        for sig in pre:
            pre_b, post_b = pre[sig], post.get(sig)

            for key_tok, _v in split_map(strip_outer(pre_b.summary_raw, "{", "}")):
                r = parse_objref(key_tok)
                if r is None:
                    continue
                objtype, ref = r
                i = nid(sig, objtype, ref)
                if i not in nodes:
                    cls, mname = soot_sig_parts(sig)
                    nodes[i] = dict(id=i, method=sig, cls=cls, mname=mname,
                                    bci=ref, objType=objtype,
                                    kind="object" if objtype in ("internal", "external")
                                    else "param",
                                    label="%s@%s.%s:%s" % (objtype, cls.split(".")[-1],
                                                           mname, ref),
                                    escapeStatus=None)

            if post_b is not None:
                for key_tok, val in split_map(strip_outer(post_b.summary_raw, "{", "}")):
                    r = parse_objref(key_tok)
                    if r is None:
                        continue
                    i = nid(sig, r[0], r[1])
                    if i not in nodes:
                        # <returnValue,N> is a key of the RESOLVED summary only - it is never
                        # a key of the pre-resolution one, because it is the callee's return
                        # slot rather than an object the method's own summary is defined over.
                        # Seeding nodes from the pre block alone therefore dropped every
                        # returnValue node, which silently zeroed EscapeReason.RETURNED (the
                        # only reason that can land on one) and lost their resolved status.
                        # objs is still internal+external, so no previously reported number
                        # moves; this is additive.
                        cls, mname = soot_sig_parts(sig)
                        nodes[i] = dict(id=i, method=sig, cls=cls, mname=mname,
                                        bci=r[1], objType=r[0],
                                        kind="object" if r[0] in ("internal", "external")
                                        else "param",
                                        label="%s@%s.%s:%s" % (r[0], cls.split(".")[-1],
                                                               mname, r[1]),
                                        escapeStatus=None)
                    st = sorted(t.strip() for t in
                                split_top_states(strip_outer(val, "[", "]")))
                    nodes[i]["escapeStatus"] = ",".join(st) if st else "unknown"

            # heap edges from the PTG Fields: map
            for owner, fname, tgt in parse_fields(pre_b.fields_raw):
                a, b = nid(sig, owner[0], owner[1]), nid(sig, tgt[0], tgt[1])
                if a in nodes and b in nodes:
                    prov = "FIELD_LOAD" if tgt[0] == "external" else "CONTAINMENT"
                    heap_edges.append((a, b, fname, prov))

            # dependency edges from the pre-resolution summary
            for key_tok, val in split_map(strip_outer(pre_b.summary_raw, "{", "}")):
                r = parse_objref(key_tok)
                if r is None:
                    continue
                src = nid(sig, r[0], r[1])
                for tok in split_top_states(strip_outer(val, "[", "]")):
                    kind, cv = parse_cv(tok)
                    if kind != "CV":
                        continue
                    prov = ("RETURN" if cv["objType"] == "returnValue"
                            else "ARGUMENT" if cv["isReal"] else "CONTAINMENT")
                    dep_edges.append((src, nid(cv["method"], cv["objType"], cv["objRef"]),
                                      prov))

    # ---- escape reasons, additive, joined on (method, bci, objectType) ------------
    if reasons is not None:
        for n in nodes.values():
            try:
                key = (n["method"], int(n["bci"]), n["objType"])
            except (TypeError, ValueError):
                n.update(reason_fields([], None if getattr(reasons, "own", None) is None else []))
                continue
            n.update(reason_fields(reasons.get(key, []), own_of(reasons, key)))

    return nodes, heap_edges, dep_edges, files


def split_top_states(body):
    from info_to_graph import split_top
    return split_top(body)


def dist(counter, top=12):
    return ", ".join("%d×%d" % (n, c) for n, c in
                     sorted(counter.items(), key=lambda kv: -kv[0])[:top])


def main(args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    # More than one prefix because an application is not always one package. avrora is
    # `avrora.` alone, but xalan's own classes are org.apache.xalan, org.apache.xpath and
    # org.apache.xml, and filtering to one of the three would silently drop two thirds of
    # the program while still printing a confident number.
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--jdk", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--drilldown-max", type=int, default=12,
                    help="max objects in the drill-down method chosen for rendering")
    ap.add_argument("--reasons", default=None,
                    help="path to <dirname>.reasons; default: the one in --info-dir")
    ap.add_argument("--require-reasons", action="store_true")
    ap.add_argument("--top-reason-sets", type=int, default=20,
                    help="reason sets shown individually in figure 1; the rest are aggregated")
    a = ap.parse_args(args)

    os.makedirs(a.out_dir, exist_ok=True)

    rpath = find_reasons_file(a.info_dir, a.reasons)
    if rpath is None:
        if a.require_reasons:
            raise SystemExit("no .reasons file in %s and --require-reasons was given"
                             % a.info_dir)
        reasons = None
        print("note: no .reasons file in %s; no reason fields will be written" % a.info_dir,
              file=sys.stderr)
    else:
        reasons = read_reasons(rpath)

    nodes, heap_edges, dep_edges, files = build(a.info_dir, a.class_prefix, reasons)

    objs = {i: n for i, n in nodes.items() if n["kind"] == "object"}
    internal = {i: n for i, n in objs.items() if n["objType"] == "internal"}

    print("== %s" % a.label)
    print("   .info files read        : %d (prefixes %s)"
          % (len(files), ", ".join(a.class_prefix)))
    print("   methods                 : %d" % len({n['method'] for n in nodes.values()}))
    print("   objects (int + ext)     : %d" % len(objs))
    print("     internal (allocations): %d" % len(internal))
    print("     external (call/load)  : %d" % (len(objs) - len(internal)))

    st = Counter(n["escapeStatus"] for n in objs.values())
    print("   resolved status         : %s"
          % ", ".join("%s=%d" % (k, v) for k, v in sorted(st.items(), key=str)))
    ne = st.get("NoEscape", 0)
    if objs:
        print("   NoEscape share          : %.2f%%" % (100.0 * ne / len(objs)))

    # ---- Definition S -------------------------------------------------------------
    s_groups = defaultdict(list)
    for i, n in objs.items():
        s_groups[n["escapeStatus"] or "unresolved"].append(i)
    print("\n   -- Definition S (equal resolved EscapeStatus)")
    print("   sets                    : %d" % len(s_groups))
    for k, v in sorted(s_groups.items(), key=lambda kv: -len(kv[1])):
        print("     %-12s %8d objects" % (k, len(v)))

    # ---- Definition C -------------------------------------------------------------
    hp = [e for e in heap_edges if e[3] == "CONTAINMENT"]
    ld = [e for e in heap_edges if e[3] == "FIELD_LOAD"]
    print("\n   -- heap edges from PTG Fields:")
    print("   CONTAINMENT (store)     : %d" % len(hp))
    print("   FIELD_LOAD  (load)      : %d" % len(ld))

    for name, edges in (("CONTAINMENT only", hp), ("CONTAINMENT + FIELD_LOAD", heap_edges)):
        adj = defaultdict(list)
        for s, d, _f, _p in edges:
            adj[s].append(d)
        comp = tarjan_scc(sorted(objs), adj)
        sizes = Counter(Counter(comp.values()).values())
        nontrivial = sum(c for s, c in sizes.items() if s > 1)
        print("\n   -- Definition C (SCC over %s)" % name)
        print("   sets                    : %d" % len(set(comp.values())))
        print("   non-singleton SCCs      : %d" % nontrivial)
        print("   SCC size distribution   : %s" % (dist(sizes) or "-"))
        if nontrivial == 0:
            print("   => every SCC is a singleton: Clustering-Design 3.3 says option A is dead")

    outdeg = Counter(len(v) for v in
                     _adj_of(heap_edges).values()) if heap_edges else Counter()
    print("\n   -- out-degree over heap edges (M5)")
    print("   distribution            : %s" % (dist(outdeg) or "-"))

    dep_by_prov = Counter(p for _s, _d, p in dep_edges)
    print("\n   -- dependency edges from summaries")
    for k, v in sorted(dep_by_prov.items()):
        print("     %-12s %8d" % (k, v))

    # ---- condensation graph (one node per S set) -----------------------------------
    cond_nodes, cond_edges = [], []
    sid = {k: n for n, k in enumerate(sorted(s_groups))}
    for k, members in sorted(s_groups.items()):
        cond_nodes.append(dict(
            id="S%d" % sid[k], kind="object", method=None, bci=None, type=k,
            isReal=None, label="%s  (%d objects)" % (k, len(members)),
            escapeStatus=k, equiEscapeSet=sid[k], equiEscapeSetS=sid[k],
            equiEscapeSetC=sid[k], memberCount=len(members)))
    # An endpoint may be a PARAMETER node (e.g. <parameter,-1>.f = <external,1> from a load
    # on `this`), which is not an object and has no equi-escape set. Those endpoints are
    # bucketed as "parameter" rather than dropped, so the condensation still accounts for
    # every edge.
    def bucket(i):
        n = nodes.get(i)
        if n is None:
            return "unknown"
        if n["kind"] != "object":
            return "parameter"
        return n["escapeStatus"] or "unresolved"

    pair = Counter()
    for s, d, _f, p in heap_edges:
        pair[(bucket(s), bucket(d), p)] += 1
    for extra in sorted({b for k in pair for b in k[:2]} - set(s_groups)):
        sid[extra] = len(sid)
        cond_nodes.append(dict(
            id="S%d" % sid[extra], kind="param" if extra == "parameter" else "object",
            method=None, bci=None, type=extra, isReal=None,
            label="%s  (not an allocation)" % extra, escapeStatus=None,
            equiEscapeSet=None, equiEscapeSetS=None, equiEscapeSetC=None,
            memberCount=0))
    for (ks, kd, p), c in sorted(pair.items()):
        cond_edges.append(dict(fromNode="S%d" % sid[ks], toNode="S%d" % sid[kd],
                               fieldPath=["%d edges" % c], provenance=p, derived=False))

    meta = dict(jdk=a.jdk, config=a.config,
                filter="application classes only, .info prefixes %s"
                       % ", ".join(a.class_prefix),
                reasons=(describe_reasons() if reasons is not None
                         else "NOT AVAILABLE: this run was made by an uninstrumented Stava"),
                definition="S", definitionS="equal resolved EscapeStatus after purge()",
                definitionC="same SCC over heap edges",
                view="CONDENSATION: one node per equi-escape set, not one node per object. "
                     "%d objects condensed to %d sets." % (len(objs), len(s_groups)),
                benchmark=a.label)
    with open(os.path.join(a.out_dir, "graph-condensation.json"), "w") as fh:
        json.dump({"meta": meta, "nodes": cond_nodes, "edges": cond_edges},
                  fh, indent=2, sort_keys=True)
        fh.write("\n")

    # ---- drill-down: a real method small enough to read ----------------------------
    per_method = defaultdict(lambda: {"objs": [], "edges": []})
    for i, n in objs.items():
        per_method[n["method"]]["objs"].append(i)
    for s, d, f, p in heap_edges:
        # group by the edge's own method; the source may be a parameter node, which is in
        # `nodes` but not in `objs`
        owner = nodes.get(s) or nodes.get(d)
        if owner is None:
            continue
        per_method[owner["method"]]["edges"].append((s, d, f, p))
    best = None
    for m, v in sorted(per_method.items()):
        if 1 < len(v["objs"]) <= a.drilldown_max and v["edges"]:
            score = (len(v["edges"]), -len(v["objs"]))
            if best is None or score > best[0]:
                best = (score, m, v)
    if best:
        _sc, m, v = best
        keep = set(v["objs"])
        # pull in any parameter endpoints the method's edges touch, so no edge is orphaned
        for s, d, _f, _p in v["edges"]:
            for e in (s, d):
                if e in nodes and nodes[e]["method"] == m:
                    keep.add(e)
        dn = [dict(id=i, kind=nodes[i]["kind"], method=nodes[i]["method"],
                   bci=nodes[i]["bci"], type=nodes[i]["objType"], isReal=None,
                   label=nodes[i]["label"], escapeStatus=nodes[i]["escapeStatus"])
              for i in sorted(keep)]
        sset = {}
        for n in dn:
            k = n["escapeStatus"] or "unresolved"
            sset.setdefault(k, len(sset))
            n["equiEscapeSetS"] = n["equiEscapeSetC"] = n["equiEscapeSet"] = sset[k]
        de = [dict(fromNode=s, toNode=d, fieldPath=[f], provenance=p, derived=False)
              for s, d, f, p in v["edges"] if s in keep and d in keep]
        for n in dn:
            if n["escapeStatus"] in ("Escape", "NoEscape"):
                de.append(dict(fromNode=n["id"], toNode="sink:" + n["escapeStatus"],
                               fieldPath=[], provenance="SINK", derived=False))
        for s in ("Escape", "NoEscape"):
            dn.append(dict(id="sink:" + s, kind="sink", method=None, bci=None, type=s,
                           isReal=None, label=s, escapeStatus=s,
                           equiEscapeSet=None, equiEscapeSetS=None, equiEscapeSetC=None))
        dmeta = dict(meta)
        dmeta["view"] = ("DRILL-DOWN: one method of %s, not the whole benchmark. "
                         "Chosen as the method with the most heap edges among those with "
                         "at most %d objects." % (a.label, a.drilldown_max))
        with open(os.path.join(a.out_dir, "graph-drilldown.json"), "w") as fh:
            json.dump({"meta": dmeta, "nodes": dn, "edges": de}, fh, indent=2,
                      sort_keys=True)
            fh.write("\n")
        print("\n   -- drill-down method chosen")
        print("      %s" % m)
        print("      %d objects, %d heap edges" % (len(keep), len(de)))

    # ---- full app-only graph, for the interactive explorer --------------------------
    # Every node the edges touch, including callee-parameter and returnValue nodes that live
    # in methods we did not read (JDK), which are marked libraryBoundary so the explorer can
    # show where the application graph stops.
    full_nodes = {}
    for i, n in nodes.items():
        full_nodes[i] = dict(id=i, kind=n["kind"], method=n["method"], cls=n["cls"],
                             mname=n["mname"], bci=n["bci"], objType=n["objType"],
                             label=n["label"], escapeStatus=n["escapeStatus"],
                             libraryBoundary=False,
                             escapeReasons=n.get("escapeReasons"),
                             reasonCount=n.get("reasonCount"),
                             realReasonCount=n.get("realReasonCount"),
                             surrenderReasonCount=n.get("surrenderReasonCount"),
                             ownReasons=n.get("ownReasons"),
                             inheritedReasons=n.get("inheritedReasons"))
    full_edges = []
    for s, d, f, p in heap_edges:
        full_edges.append(dict(f=s, t=d, p=p, lab=f))
    for s, d, p in dep_edges:
        full_edges.append(dict(f=s, t=d, p=p, lab=""))
    for e in full_edges:
        for side in ("f", "t"):
            i = e[side]
            if i in full_nodes:
                continue
            objtype, sig, ref = i.split("|", 2)
            cls, mname = (soot_sig_parts(sig) if sig.startswith("<") else (sig, ""))
            full_nodes[i] = dict(id=i, kind="param", method=sig, cls=cls, mname=mname,
                                 bci=ref, objType=objtype,
                                 label="%s@%s.%s:%s" % (objtype, cls.split(".")[-1],
                                                        mname, ref),
                                 escapeStatus=None,
                                 libraryBoundary=not any(cls.startswith(p)
                                                         for p in a.class_prefix),
                                 # a node the edges reach but no .info was read for: no
                                 # reason data exists, which is not the same as an empty set
                                 escapeReasons=None, reasonCount=None,
                                 realReasonCount=None, surrenderReasonCount=None,
                                 ownReasons=None, inheritedReasons=None)
    for i, n in full_nodes.items():
        k = n["escapeStatus"] or "unresolved"
        n["s"] = sid.get(k) if n["kind"] == "object" else None
    with open(os.path.join(a.out_dir, "graph-full.json"), "w") as fh:
        json.dump({"meta": meta, "nodes": sorted(full_nodes.values(),
                                                 key=lambda x: x["id"]),
                   "edges": full_edges}, fh, separators=(",", ":"), sort_keys=True)
        fh.write("\n")
    print("\n   -- full app graph for the explorer")
    print("      nodes %d, edges %d" % (len(full_nodes), len(full_edges)))
    lib = sum(1 for n in full_nodes.values() if n["libraryBoundary"])
    print("      library-boundary nodes: %d" % lib)

    # ---- reason multiplicity ---------------------------------------------------------
    wrote_reasons = ""
    if reasons is not None:
        objlist = list(objs.values())
        rc = Counter(n.get("reasonCount") or 0 for n in objlist)
        rr = Counter(n.get("realReasonCount") or 0 for n in objlist)
        print("\n   -- escape reason multiplicity (%s)" % os.path.basename(rpath))
        print("   objects with >=1 reason  : %d of %d"
              % (sum(c for k, c in rc.items() if k), len(objlist)))
        # Percentages are of the whole population, bucket 0 included, so each series sums to
        # 100 %. Quoting a bucket without its share invites reading 3,057 as large when it is
        # 57.7 % of one benchmark and 45.4 % of another.
        n_obj = len(objlist) or 1
        print("   reasonCount histogram    : %s"
              % ", ".join("%d:%d (%.1f%%)" % (k, rc[k], 100.0 * rc[k] / n_obj)
                          for k in sorted(rc)))
        print("   realReasonCount histogram: %s"
              % ", ".join("%d:%d (%.1f%%)" % (k, rr[k], 100.0 * rr[k] / n_obj)
                          for k in sorted(rr)))
        # the number worth quoting: how much of the multiplicity is Stava giving up
        # A REDISTRIBUTION, not a share. An object with one real and one surrender reason
        # leaves bucket 2 and joins bucket 1, so it shows as +1 at 2 and -1 at 1. Quoting the
        # per-bucket delta as "the analysis-artefact share" was wrong and went unnoticed while
        # every value was 0; xalan is the first run where it is not.
        gap = {k: rc.get(k, 0) - rr.get(k, 0) for k in set(rc) | set(rr)}
        n_surr = sum(1 for n in objlist if (n.get("surrenderReasonCount") or 0) > 0)
        print("   all-minus-real per count : %s   (redistribution, not a share)"
              % ", ".join("%d:%+d" % (k, gap[k]) for k in sorted(gap)))
        print("   objects with a surrender reason : %d of %d  <- the artefact count"
              % (n_surr, len(objlist)))

        # A raw per-reason count is dominated by component-wide attribution and badly
        # overstates how many objects independently have the property. Measured across six
        # DaCapo benchmarks: pmd reports THREAD_REACHABLE_CLASS on 955 objects, of which 955
        # are one SCC carrying a single thread-reachable class between them -- 0 independent.
        # MONITOR reports 6,922 on fop, of which 15 are outside the blob.
        #
        # So report both. A "blob" is a reason-set cluster big enough and wide enough that it
        # can only be one dependency component reported once per member; every reason in its
        # set is inflated to its size. Thresholds are arbitrary but the blobs are listed by
        # name so the reader can judge.
        BLOB_MIN_REASONS, BLOB_MIN_MEMBERS = 4, 50
        setcount = Counter(tuple(n.get("escapeReasons") or []) for n in objlist)
        blobs = {k for k, c in setcount.items()
                 if len(k) >= BLOB_MIN_REASONS and c >= BLOB_MIN_MEMBERS}
        per_reason, per_reason_net = Counter(), Counter()
        for n in objlist:
            rs = tuple(n.get("escapeReasons") or [])
            for r in rs:
                per_reason[r] += 1
                if rs not in blobs:
                    per_reason_net[r] += 1
        blob_members = sum(c for k, c in setcount.items() if k in blobs)
        print("   per-reason object counts : raw, then excluding component blobs")
        print("     %-30s %8s %8s %8s %8s"
              % ("reason", "raw", "raw%", "net", "net%"))
        for r, c in sorted(per_reason.items(), key=lambda kv: -kv[1]):
            net = per_reason_net.get(r, 0)
            flag = "  <- almost entirely blob" if c and net / float(c) < 0.1 else ""
            print("     %-30s %8d %7.1f%% %8d %7.1f%%  %s%s"
                  % (r, c, 100.0 * c / n_obj, net, 100.0 * net / n_obj,
                     "surrender" if r in SURRENDER else "real", flag))
        print("   component blobs          : %d set(s), %d of %d objects (%.1f%%)"
              % (len(blobs), blob_members, len(objlist),
                 100.0 * blob_members / max(1, len(objlist))))
        for k in sorted(blobs, key=lambda k: -setcount[k]):
            print("     %6d objects  %s" % (setcount[k], ", ".join(k)))

        # Patch 0005 makes the blob question exact: per reason, on how many objects did it
        # fire on the object itself, and on how many was it stamped by the component. The
        # 4/50 heuristic above is kept for pre-0005 runs and for comparison.
        per_reason_own = Counter()
        split = bool(objlist) and all(n.get("ownReasons") is not None for n in objlist)
        if split:
            for n in objlist:
                for r in n["ownReasons"]:
                    per_reason_own[r] += 1
            n_inh = sum(1 for n in objlist if n.get("inheritedReasons"))
            print("   own vs inherited (exact, patch 0005): %d of %d objects carry an inherited "
                  "reason" % (n_inh, len(objlist)))
            print("     %-30s %8s %8s %9s" % ("reason", "objects", "own", "inherited"))
            for r, c in sorted(per_reason.items(), key=lambda kv: -kv[1]):
                print("     %-30s %8d %8d %9d" % (r, c, per_reason_own[r], c - per_reason_own[r]))
        else:
            print("   own vs inherited: not recorded by this run (predates patch 0005)")

        single = Counter()
        for n in objlist:
            rs = n.get("escapeReasons") or []
            if len(rs) == 1:
                single[rs[0]] += 1
        n_single = sum(single.values()) or 1
        print("   single-reason attribution (figure 3): %d objects, %.1f%% of all %d"
              % (sum(single.values()), 100.0 * sum(single.values()) / n_obj, n_obj))
        print("     %-30s %8s %9s %9s" % ("reason", "objects", "of single", "of all"))
        for r, c in sorted(single.items(), key=lambda kv: -kv[1]):
            print("     %-30s %8d %8.1f%% %8.1f%%"
                  % (r, c, 100.0 * c / n_single, 100.0 * c / n_obj))

        # Both halves of the invariant, printed on every run.
        #   Escape with 0 reasons  -> a firing site was missed, or a component member was not
        #                             stamped. Must be 0.
        #   NoEscape with >0       -> the side map is APPEND-ONLY and the analysis is not:
        #                             a statement re-applied on a later worklist iteration can
        #                             `summary.put` a fresh EscapeStatus over one a store had
        #                             already escaped. The reason is then true of the run and
        #                             false of the verdict. Small but not zero; quoted, never
        #                             silently dropped.
        esc0 = sum(1 for n in objlist
                   if n.get("escapeStatus") == "Escape" and not (n.get("escapeReasons") or []))
        noesc = [n for n in objlist
                 if n.get("escapeStatus") == "NoEscape" and (n.get("escapeReasons") or [])]
        print("   Escape with 0 reasons    : %d  <- integrity check" % esc0)
        print("   NoEscape with >0 reasons : %d  <- retracted by a later worklist iteration"
              % len(noesc))
        for n in noesc[:5]:
            print("       %s  %s" % (n["label"], ",".join(n["escapeReasons"])))

        clusters, other = reason_set_clusters(objlist, a.top_reason_sets)
        rmeta = dict(meta)
        rmeta["view"] = ("REASON-SET CLUSTERS: one entry per DISTINCT escape-reason set over "
                         "%d objects, not one per object. The top %d sets by population are "
                         "listed individually; the remainder is one aggregated entry whose "
                         "member count is carried." % (len(objlist), a.top_reason_sets))
        with open(os.path.join(a.out_dir, "graph-reasonsets.json"), "w") as fh:
            json.dump({"meta": rmeta, "clusters": clusters, "other": other,
                       "totalObjects": len(objlist),
                       "reasonCountHistogram": {str(k): rc[k] for k in sorted(rc)},
                       "realReasonCountHistogram": {str(k): rr[k] for k in sorted(rr)},
                       "singleReasonAttribution": dict(single),
                       "perReasonObjectCounts": dict(per_reason),
                       "perReasonOwnObjectCounts": dict(per_reason_own) if split else None,
                       "escapeWithZeroReasons": esc0},
                      fh, indent=2, sort_keys=True)
            fh.write("\n")
        wrote_reasons = ", graph-reasonsets.json"

    print("\n   wrote %s/graph-condensation.json, graph-drilldown.json, graph-full.json%s"
          % (a.out_dir, wrote_reasons))


def _adj_of(edges):
    adj = defaultdict(list)
    for s, d, _f, _p in edges:
        adj[s].append(d)
    return adj


if __name__ == "__main__":
    main()
