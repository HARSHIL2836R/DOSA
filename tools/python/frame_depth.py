#!/usr/bin/env python3
"""frame_depth.py - the frame-depth axis of Meet 5: how many frames DOWN each allocation site
is passed. 02-Current-Work/01-Design/2026-08-25-Escape-Reason-And-Frame-Depth.md §2.

    python3 tools/python/frame_depth.py --run-dir /tmp/rv/p6out/avrora-false --class-prefix avrora. \
        --label "avrora false" [--json out.json]

DEFINITION (design note §2.1). An ARGUMENT edge is a pre-resolution conditional value
<callee,<parameter,k>,[T]> on an object: the object is passed to that callee as argument k.
    down(o) = longest path from o over ARGUMENT edges, in the condensation of that graph
The walk continues from the callee's parameter node, so a parameter passed on counts again.
Condensation first, because recursion makes the raw longest path unbounded; a site whose
descent enters a recursive component is counted separately.

WHAT IS REPORTED, per application allocation site (.alloc NEW), split by Stava's verdict:
  max    the longest path, every call-graph target of a call taken as possible
  min    at each call site, the target with the shortest onward path (design note §2.2 item 1:
         a megamorphic call produces an edge to every target, so max can describe the call
         graph rather than the program). Call sites come from .cg (patch 0006); an edge .cg
         does not place is its own call site.
  noinit the max again with calls to constructors weighted 0: every allocation is passed to
         its <init>, and <init> to its super's, so this is the depth beyond construction.
For a NoEscape site, max is the inlining depth HotSpot would need to scalar-replace it (design
note §1.1): HotSpot only scalar-replaces an allocation whose uses are all inlined.

The descent is followed into library methods: the run directory holds every analysed method.
A callee with no summary ends the path there, one frame down.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "extract", "python"))
from bci_to_source import parse_soot_sig  # noqa: E402
from capture_level import load, load_cg  # noqa: E402
from info_to_graph import (parse_info, parse_objref, split_map, split_passes,  # noqa: E402
                           strip_outer, tarjan_scc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--sites-out", default=None,
                    help="JSON list of [method, bci, verdict, max, min, noinit] for every site")
    a = ap.parse_args()

    name = os.path.basename(glob.glob(os.path.join(a.run_dir, "*.reasons"))[0])[:-len(".reasons")]
    pre, _fields, _ret = load(a.run_dir)
    cgp = os.path.join(a.run_dir, name + ".cg")
    sites_of = defaultdict(list)          # (method, obj) -> [(bci, k, {targets})]
    if os.path.exists(cgp):
        by_site = defaultdict(set)
        for callee, es in load_cg(cgp).items():
            for caller, bci, args in es:
                for k, objs in args.items():
                    for o in objs:
                        by_site[(caller, o, bci, k)].add(callee)
        for (caller, o, bci, k), ts in by_site.items():
            sites_of[(caller, o)].append((bci, k, ts))

    def is_app(sig):
        q = parse_soot_sig(sig)
        return q is not None and any(q[0].startswith(x) for x in a.class_prefix)

    # ARGUMENT edges
    edges = defaultdict(set)
    for m, summ in pre.items():
        for o, states in summ.items():
            for s in states:
                if s[0] == "CV" and s[2][0] == "parameter" and s[4] and s[1]:
                    edges[(m, o)].add((s[1], s[2][1]))

    kinds = {}
    ap_ = os.path.join(a.run_dir, name + ".alloc")
    if os.path.exists(ap_):
        with open(ap_, encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                kinds[(p[0], int(p[1]), p[2])] = p[3]
    targets = sorted((m, o) for m, summ in pre.items() if is_app(m) for o in summ
                     if o[0] == "internal"
                     and (not kinds or kinds.get((m, o[1], "internal")) == "NEW"))

    # reachable subgraph, condensed
    seen, stack = set(targets), list(targets)
    adj = {}
    while stack:
        x = stack.pop()
        succ = sorted((t, ("parameter", k)) for t, k in edges.get(x, ()))
        adj[x] = succ
        for y in succ:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    comp = tarjan_scc(sorted(seen), adj)
    size = Counter(comp.values())
    self_loop = {comp[x] for x in adj for y in adj[x] if y == x}
    recursive = {c for c, n in size.items() if n > 1} | self_loop

    def group_calls(x):
        """x's out-edges grouped into call sites: [[(callee, k), ...], ...]."""
        outs = {(t, k) for t, k in edges.get(x, ())}
        groups, placed = [], set()
        for bci, k, ts in sorted(sites_of.get(x, ()), key=lambda z: (z[0], z[1])):
            g = [(t, k) for t in sorted(ts) if (t, k) in outs]
            if g:
                groups.append(g)
                placed |= set(g)
        groups += [[e] for e in sorted(outs - placed)]
        return groups

    memo = {"max": {}, "min": {}, "noinit": {}}
    enters_rec = {}

    def depth(x, mode):
        """Longest path from x's component, edges inside a component weighted 0."""
        c = comp[x]
        if c in memo[mode]:
            return memo[mode][c]
        memo[mode][c] = 0
        best, rec = 0, c in recursive
        todo, done = [x], {x}
        while todo:                              # every member of x's component
            y = todo.pop()
            for g in group_calls(y):
                vals = []
                for t, k in g:
                    z = (t, ("parameter", k))
                    w = 0 if (mode == "noinit" and ": void <init>(" in t) else 1
                    if comp.get(z) == c:
                        if z not in done:
                            done.add(z)
                            todo.append(z)
                        vals.append(0)
                        continue
                    if z not in comp:
                        vals.append(w)
                        continue
                    vals.append(w + depth(z, mode))
                    rec = rec or enters_rec.get(comp[z], False)
                if vals:
                    best = max(best, min(vals) if mode == "min" else max(vals))
        memo[mode][c] = best
        enters_rec[c] = rec
        return best

    verdict = {}
    for path in sorted(glob.glob(os.path.join(a.run_dir, "*.info"))):
        base = os.path.basename(path)
        if not any(base.startswith(p) for p in a.class_prefix):
            continue
        _pre, post = split_passes(parse_info(path))
        for sig, b in post.items():
            for otok, stok in split_map(strip_outer(b.summary_raw, "{", "}")):
                o = parse_objref(otok)
                if o and o[0] == "internal":
                    verdict[(sig, o)] = "NoEscape" if "NoEscape" in stok else "Escape"

    rows = []
    for x in targets:
        rows.append((x, verdict.get(x, "?"), depth(x, "max"), depth(x, "min"),
                     depth(x, "noinit"), enters_rec.get(comp[x], False)))

    out = {"label": a.label, "sites": len(rows), "byVerdict": {}}
    print("== %s  (%d application allocation sites; %d nodes reached, %d recursive components)"
          % (a.label, len(rows), len(seen), len(recursive)))
    for v in ("NoEscape", "Escape", "?"):
        sub = [r for r in rows if r[1] == v]
        if not sub:
            continue
        h = {m: Counter(min(r[i], 10) for r in sub) for m, i in (("max", 2), ("min", 3),
                                                                ("noinit", 4))}
        rec = sum(1 for r in sub if r[5])
        print("   %s: %d sites, %d whose descent enters recursion (depth there counted once)"
              % (v, len(sub), rec))
        print("      %-7s %s" % ("depth", " ".join("%6s" % (str(d) if d < 10 else "10+")
                                                  for d in range(11))))
        for m in ("max", "min", "noinit"):
            print("      %-7s %s" % (m, " ".join("%6d" % h[m].get(d, 0) for d in range(11))))
        out["byVerdict"][v] = {"sites": len(sub), "recursive": rec,
                               "hist": {m: {str(d): h[m].get(d, 0) for d in range(11)}
                                        for m in h}}
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
    if a.sites_out:
        with open(a.sites_out, "w", encoding="utf-8") as fh:
            json.dump([[x[0], x[1][1], v, mx, mn, ni] for x, v, mx, mn, ni, _r in rows], fh,
                      indent=0)


if __name__ == "__main__":
    sys.setrecursionlimit(1000000)
    import threading
    threading.stack_size(512 * 1024 * 1024)
    t = threading.Thread(target=main)
    t.start()
    t.join()
