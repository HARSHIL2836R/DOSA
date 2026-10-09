#!/usr/bin/env python3
"""source_check.py - does the downloaded source match the bytecode Stava analysed?

    python3 tools/python/source_check.py --bench avrora --alloc /tmp/rv/p6info/avrora-false/dacapo.alloc \
        --class-prefix avrora.

For every application allocation site (.alloc KIND NEW), extract/source_index.Sources.place()
takes the line the class file's LineNumberTable gives and checks that the source there allocates
the site's type (see alloc_pattern). Outcomes:
  exact line            the line the class file names shows the allocation
  found N lines away    the source text differs from the analysed build; the allocation was
                        found within source_index.RADIUS lines, and a snippet shows that line
  not placed            not found within the radius; no snippet is ever shown for it
  compiler-generated    javac's own allocations (assert, the class$ helper of a 1.4 class
                        literal): no source text to match
  no source file        the class is not in the release (fop's build-generated fonts.base14)
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "extract", "python"))
from bci_to_source import parse_soot_sig  # noqa: E402
from source_index import Sources  # noqa: E402


def read_sites(path, prefixes):
    sets = {}
    with open(path[:-len(".alloc")] + ".allocsets", encoding="utf-8") as fh:
        for line in fh:
            sid, _, body = line.rstrip("\n").partition("\t")
            sets[sid] = body
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m, b, t, k, s = line.rstrip("\n").split("\t")
            if k != "NEW" or t != "internal":
                continue
            q = parse_soot_sig(m)
            if q is None or not any(q[0].startswith(p) for p in prefixes):
                continue
            ty = sets.get(s, "?|?|?").split(";")[0].rsplit("|", 1)[-1]
            out.append((m, int(b), ty))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--alloc", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()
    src = Sources(a.bench)
    sites = read_sites(a.alloc, a.class_prefix)
    outcome, missing, bad = Counter(), Counter(), []
    for m, b, ty in sites:
        q = parse_soot_sig(m)
        if q[1] == "class$" or ty in ("java.lang.AssertionError", "java.lang.NoClassDefFoundError"):
            outcome["compiler-generated"] += 1
            continue
        loc = src.place(m, b, "internal", ty)
        if "error" in loc:
            if loc["error"].startswith("no source file"):
                outcome["no source file"] += 1
                missing[q[0].rsplit(".", 1)[0]] += 1
            elif loc["error"].startswith("line does not"):
                outcome["not placed"] += 1
                bad.append((m, b, ty, loc.get("file"), loc.get("line")))
            else:
                outcome["no line: " + loc["error"]] += 1
            continue
        outcome["exact line" if loc["shift"] == 0 else "found within %d lines" % 20] += 1
    n = len(sites)
    placed = outcome["exact line"] + outcome["found within 20 lines"]
    print("== %s: %d application allocation sites; of %d with source text, %.1f %% exact, "
          "%.1f %% placed"
          % (a.bench, n, placed + outcome["not placed"],
             100.0 * outcome["exact line"] / max(1, placed + outcome["not placed"]),
             100.0 * placed / max(1, placed + outcome["not placed"])))
    for k, v in outcome.most_common():
        print("   %-40s %6d  %5.1f %%" % (k, v, 100.0 * v / n))
    if missing:
        print("   packages with no source file: %s" % missing.most_common(4))
    for x in bad[:a.show]:
        print("   not placed: %s bci %d (%s) %s:%s" % (x[0][:80], x[1], x[2], x[3], x[4]))


if __name__ == "__main__":
    main()
