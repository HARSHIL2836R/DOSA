#!/usr/bin/env python3
"""viz_audit.py - checks the escape-reason figures against the objectives in
02-Current-Work/02-Specs/2026-09-14-Viz-Faithfulness-Audit.md.

    python3 tools/viz_audit.py --info-dir DIR --class-prefix avrora. \
        --figures render/figures/avrora-p3-reason --label avrora

DIR must hold the application .info files plus the run's .reasons (and .via for roots mode),
exactly as benchmark_scale.py is fed. Checks, each printed with its objective id:

  O5  every number in the figure .dot tables equals the number recomputed here (--mode says
      which reasons the figures were drawn from: raw before patch 0004, roots after)
  O3/O4  Escape <=> non-empty reason set over the figure population, raw and roots
  O1  what the counted population is made of: internal allocations vs externals, and where
      each external came from (call result / field read / no provenance left)
  O2  propagated reasons left in the population, raw vs roots
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from benchmark_scale import build  # noqa: E402
from info_to_graph import (REASONS_PROPAGATED, SURRENDER, find_reasons_file,  # noqa: E402
                           read_reasons)


def tokens(st):
    return {t.strip() for t in (st or "").split(",")}


def dot_table(path):
    """-> list of rows (list of cell strings) from the one HTML-like TABLE in a .dot."""
    s = open(path, encoding="utf-8").read()
    rows = re.findall(r"<TR>(.*?)</TR>", s)
    return [re.findall(r"<TD>(.*?)</TD>", r) for r in rows][1:]


def dot_clusters(path):
    s = open(path, encoding="utf-8").read()
    out = []
    for lbl in re.findall(r'c\d+ \[label="(.*?)"', s):
        head, _, tail = lbl.partition("\\n")
        m = re.search(r"\| (\d+) objects", tail)
        out.append((head, int(m.group(1)) if m else None))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--figures", default=None, help="prefix of the existing reason figures")
    ap.add_argument("--label", required=True)
    ap.add_argument("--mode", choices=["raw", "roots"], default="raw",
                    help="which reasons the figures were drawn from; raw for pre-0004 figures")
    a = ap.parse_args()

    rp = find_reasons_file(a.info_dir, None)
    raw = read_reasons(rp, mode="raw")
    roots = read_reasons(rp, mode="roots")
    nodes, heap_edges, dep_edges, files = build(a.info_dir, a.class_prefix, None)

    def key(n):
        return (n["method"], int(n["bci"]), n["objType"])

    pop = [n for n in nodes.values() if n["kind"] == "object"]
    print("== %s: %d .info files, %d nodes, population (kind=object) %d"
          % (a.label, len(files), len(nodes), len(pop)))

    # ---- O5: figure numbers vs recomputed ------------------------------------------
    if a.figures:
        fm = roots if a.mode == "roots" else raw
        print("\n-- O5  figure tables vs data (%s reasons)" % a.mode)
        rc = Counter(len(fm.get(key(n), [])) for n in pop)
        real = Counter(sum(1 for r in fm.get(key(n), []) if r not in SURRENDER) for n in pop)
        bad = 0
        for row in dot_table(a.figures + "-multiplicity.dot"):
            k, allc, _, realc = int(row[0]), int(row[1]), row[2], int(row[3])
            if allc != rc[k] or realc != real[k]:
                bad += 1
                print("   MISMATCH bucket %d: figure all=%d real=%d, data all=%d real=%d"
                      % (k, allc, realc, rc[k], real[k]))
        missing = set(rc) - {int(r[0]) for r in dot_table(a.figures + "-multiplicity.dot")}
        print("   multiplicity: %d bucket mismatches, buckets absent from figure: %s"
              % (bad, sorted(missing) or "none"))
        single = Counter(fm[key(n)][0] for n in pop if len(fm.get(key(n), [])) == 1)
        fig = {r[0]: int(r[1]) for r in dot_table(a.figures + "-single.dot")}
        diffs = {r: (fig.get(r), single.get(r)) for r in set(fig) | set(single)
                 if fig.get(r) != single.get(r)}
        print("   single-reason: %d rows, %d mismatches %s" % (len(fig), len(diffs), diffs or ""))
        sets = Counter(tuple(fm.get(key(n), [])) for n in pop)
        cl = dot_clusters(a.figures + "-clusters.dot")
        cbad, drawn = 0, 0
        for head, cnt in cl:
            if head.startswith("other"):
                continue
            t = () if head == "(none)" else tuple(x.strip() for x in head.split(","))
            drawn += cnt
            if sets.get(t) != cnt:
                cbad += 1
                print("   MISMATCH cluster %s: figure %s data %s" % (head, cnt, sets.get(t)))
        other = [c for c in cl if c[0].startswith("other")]
        ocnt = other[0][1] if other else 0
        print("   clusters: %d drawn, %d mismatches; drawn %d + other %d = %d vs population %d"
              % (len(cl), cbad, drawn, ocnt, drawn + ocnt, len(pop)))

        # ---- O1 split (patch 0005): the striped counts vs recomputed ----------------------
        own = getattr(fm, "own", None)
        if own is not None:
            def inh(n):
                return bool(set(fm.get(key(n), [])) - set(own.get(key(n), [])))
            ia = Counter(len(fm.get(key(n), [])) for n in pop if inh(n))
            ir = Counter(sum(1 for r in fm.get(key(n), []) if r not in SURRENDER)
                         for n in pop if inh(n))
            sbad = 0
            for row in dot_table(a.figures + "-multiplicity.dot"):
                if len(row) < 8:
                    sbad = -1
                    break
                k = int(row[0])
                if int(row[6]) != ia[k] or int(row[7]) != ir[k]:
                    sbad += 1
                    print("   MISMATCH inherited bucket %d: figure %s/%s data %d/%d"
                          % (k, row[6], row[7], ia[k], ir[k]))
            si = Counter(fm[key(n)][0] for n in pop if len(fm.get(key(n), [])) == 1 and inh(n))
            rows3 = dot_table(a.figures + "-single.dot")
            s3 = -1 if any(len(r) < 5 for r in rows3) else sum(
                1 for r in rows3 if int(r[4]) != si.get(r[0], 0)
                or int(r[3]) != single[r[0]] - si.get(r[0], 0))
            cs = Counter(tuple(fm.get(key(n), [])) for n in pop if inh(n))
            s1 = 0
            for lbl in re.findall(r'c\d+ \[label="(.*?)"', open(a.figures + "-clusters.dot",
                                                               encoding="utf-8").read()):
                head, _, tail = lbl.partition("\\n")
                m = re.search(r"\| (\d+) inherited", tail)
                if head.startswith("other") or not m:
                    s1 += 0 if head.startswith("other") else 1
                    continue
                t = () if head == "(none)" else tuple(x.strip() for x in head.split(","))
                if int(m.group(1)) != cs.get(t, 0):
                    s1 += 1
            print("   split: objects with an inherited reason %d of %d; mismatches - "
                  "multiplicity %s, single %s, clusters %d  (-1 = figure has no split columns)"
                  % (sum(1 for n in pop if inh(n)), len(pop), sbad, s3, s1))

    # ---- O3/O4: verdict <=> reasons ------------------------------------------------
    for name, m in (("raw", raw), ("roots", roots)):
        esc_none, noesc_some, unknown = [], [], 0
        for n in pop:
            st = tokens(n.get("escapeStatus"))
            rs = m.get(key(n), [])
            if "Escape" in st and not rs:
                esc_none.append(n)
            elif "NoEscape" in st and rs:
                noesc_some.append(n)
            elif not n.get("escapeStatus") or n.get("escapeStatus") == "unknown":
                unknown += 1
        print("\n-- O3/O4 (%s)  Escape-with-no-reason %d, NoEscape-with-reasons %d, "
              "no resolved status %d" % (name, len(esc_none), len(noesc_some), unknown))
        for n in (esc_none + noesc_some)[:5]:
            print("      %s  status=%s  reasons=%s" % (n["label"], n["escapeStatus"],
                                                      m.get(key(n))))
    nesc = sum(1 for n in pop if "Escape" in tokens(n.get("escapeStatus")))
    nwith = sum(1 for n in pop if raw.get(key(n)))
    print("   Escape verdicts %d, objects with >=1 reason %d" % (nesc, nwith))

    # ---- O2: propagated reasons in the population ----------------------------------
    prop = set(REASONS_PROPAGATED)
    for name, m in (("raw", raw), ("roots", roots)):
        c = sum(1 for n in pop if prop & set(m.get(key(n), [])))
        print("\n-- O2 (%s)  population objects carrying a propagated reason: %d" % (name, c))

    # ---- O1: what the population is made of ----------------------------------------
    print("\n-- O1  population by objectType: %s" % dict(Counter(n["objType"] for n in pop)))
    ret_out = defaultdict(set)
    for s, t, prov in dep_edges:
        if prov == "RETURN":
            ret_out[s].add(t)
    loaded = {b for _a, b, _f, prov in heap_edges if prov == "FIELD_LOAD"}
    app_methods = {n["method"] for n in nodes.values()}
    cat = Counter()
    cat_esc = Counter()
    callee_app = Counter()
    for n in pop:
        if n["objType"] != "external":
            continue
        callees = {nodes[t]["method"] if t in nodes else t.split("|")[1]
                   for t in ret_out.get(n["id"], ())
                   if (nodes[t]["method"] if t in nodes else t.split("|")[1]) != n["method"]}
        is_call, is_load = bool(callees), n["id"] in loaded
        c = ("call result" if is_call and not is_load else
             "field read" if is_load and not is_call else
             "both" if is_call and is_load else "no provenance in .info")
        cat[c] += 1
        if "Escape" in tokens(n.get("escapeStatus")):
            cat_esc[c] += 1
        if is_call:
            callee_app["callee analysed (app)" if callees & app_methods
                       else "callee outside app classes"] += 1
    ext = sum(cat.values())
    print("   externals: %d" % ext)
    for c, v in cat.most_common():
        print("      %-24s %6d (%.1f %%)  escaping %d" % (c, v, 100.0 * v / max(1, ext), cat_esc[c]))
    print("   call results by callee: %s" % dict(callee_app))
    nprov = [n for n in pop if n["objType"] == "external" and not ret_out.get(n["id"])
             and n["id"] not in loaded]
    rc = Counter()
    for n in nprov:
        for r in raw.get(key(n), []) or ["(no reason)"]:
            rc[r] += 1
    print("   reasons on externals with no provenance: %s" % rc.most_common(8))
    internals = sum(1 for n in pop if n["objType"] == "internal")
    print("   population / internal allocation sites = %d / %d = %.2f"
          % (len(pop), internals, len(pop) / max(1, internals)))


if __name__ == "__main__":
    main()
