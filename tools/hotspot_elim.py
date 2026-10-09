#!/usr/bin/env python3
"""hotspot_elim.py - which allocation sites HotSpot's C2 removed, read from its compilation log.

    python3 tools/hotspot_elim.py --log hotspot.log [--out elim.tsv]

The log comes from a product JDK 8 run with
    -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=hotspot.log
C2 writes two events that remove an allocation, each followed by the JVM state of the
allocation: its bci and method first, then every caller it was inlined into.
  eliminate_allocation     escape analysis proved the object does not escape the compiled
                           method, and scalar replacement removed it (macro.cpp)
  replace_string_concat    OptimizeStringConcat replaced a StringBuilder/StringBuffer
                           append...toString chain; the state is the builder's `new` (stringopts.cpp)
Ids in the log (method, klass, type) are scoped to one compiler thread's section, so they are
resolved per <compilation_log> section.

A method C2 parsed is one it compiled, as the root of a task or inlined into one; <parse> is
C2's, so this is the denominator: a site in a method never parsed by C2 was never a candidate.

Output, one row per (event, allocating method, bci): the event, the allocated type, the method
signature in Soot's format (joins onto .reasons and .alloc), the bci, how many compilations
removed it, and in how many of those it had been inlined into another method.

What this does not show: a site removed in one compilation can still allocate in the
interpreter, in C1 code, in another inlining context, or after a deoptimisation. A row means
C2 removed the site at least once, not that the site never allocates.
"""
import argparse
import re
from collections import Counter

ATTR = re.compile(r"(\w+)='([^']*)'")
PRIM = {"int", "long", "short", "byte", "char", "boolean", "float", "double", "void"}


def jname(n):
    """HotSpot type name -> Soot type name: java/lang/String -> java.lang.String,
    [Ljava/lang/String; -> java.lang.String[], [I -> int[]."""
    dims = 0
    while n.startswith("["):
        dims += 1
        n = n[1:]
    if dims:
        n = {"I": "int", "J": "long", "S": "short", "B": "byte", "C": "char", "Z": "boolean",
             "F": "float", "D": "double"}.get(n, n[1:-1] if n.startswith("L") else n)
    return n.replace("/", ".") + "[]" * dims


def sig_of(md, names):
    """A <method .../> element -> Soot signature, e.g. <avrora.Foo: int bar(java.lang.String)>."""
    args = md.get("arguments", "").split()
    return "<%s: %s %s(%s)>" % (names.get(md.get("holder"), "?"), names.get(md.get("return"), "?"),
                                md.get("name", "?"), ",".join(names.get(x, "?") for x in args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    names, methods = {}, {}
    parsed = Counter()                   # methods C2 parsed, as the root or inlined
    rows = Counter()
    inlined = Counter()
    event, ev_type, chain = None, None, []
    tasks = 0
    with open(a.log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("<compilation_log"):
                names, methods = {}, {}
                continue
            if s.startswith("<task "):
                tasks += 1
            if s.startswith("<klass ") or s.startswith("<type "):
                d = dict(ATTR.findall(s))
                if "id" in d and "name" in d:
                    names[d["id"]] = jname(d["name"])
                continue
            if s.startswith("<method "):
                d = dict(ATTR.findall(s))
                if "id" in d:
                    methods[d["id"]] = d
                continue
            if s.startswith("<eliminate_allocation") or s.startswith("<replace_string_concat"):
                d = dict(ATTR.findall(s))
                event = "eliminate_allocation" if "eliminate_allocation" in s \
                    else "replace_string_concat"
                ev_type = names.get(d.get("type"), "java.lang.StringBuilder"
                                    if event == "replace_string_concat" else "?")
                chain = []
                continue
            if s.startswith("<parse ") and " method='" in s:
                d = dict(ATTR.findall(s))
                md = methods.get(d.get("method"))
                if md is not None:
                    parsed[sig_of(md, names)] += 1
                continue
            if event and s.startswith("<jvms "):
                d = dict(ATTR.findall(s))
                chain.append((d.get("method"), int(d.get("bci", -1))))
                continue
            if event and (s.startswith("</eliminate_allocation") or
                          s.startswith("</replace_string_concat")):
                if chain:
                    mid, bci = chain[0]
                    md = methods.get(mid)
                    sig = "?method %s" % mid if md is None else sig_of(md, names)
                    key = (event, ev_type, sig, bci)
                    rows[key] += 1
                    if len(chain) > 1:
                        inlined[key] += 1
                event, chain = None, []

    print("%d methods parsed by C2 (root or inlined)" % len(parsed))
    print("%d compile tasks; %d eliminate_allocation and %d replace_string_concat events over "
          "%d distinct (event, method, bci)" % (
              tasks, sum(v for k, v in rows.items() if k[0] == "eliminate_allocation"),
              sum(v for k, v in rows.items() if k[0] == "replace_string_concat"), len(rows)))
    by_type = Counter()
    for (ev, ty, _sig, _b), v in rows.items():
        by_type[(ev, ty)] += 1
    for (ev, ty), v in by_type.most_common(12):
        print("   %-22s %-40s %5d sites" % (ev, ty, v))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            for sig, v in sorted(parsed.items()):
                fh.write("parsed\t-\t%s\t-1\t%d\t0\n" % (sig, v))
            for (ev, ty, sig, bci), v in sorted(rows.items()):
                fh.write("%s\t%s\t%s\t%d\t%d\t%d\n" % (ev, ty, sig, bci, v, inlined[(ev, ty, sig, bci)]))


if __name__ == "__main__":
    main()
