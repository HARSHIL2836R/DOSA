#!/usr/bin/env python3
"""corpus_vs_stava.py - the corpus ownership classes next to Stava's own verdicts, and the
borrow-rule ablation.

    python3 tools/ownership/corpus_vs_stava.py

Reads build/own/<MAIN>/<MAIN>.own and <MAIN>-id.own (tools/ownership/run_corpus.sh) and, for the
programs Stava's corpus runs cover, build/out/<MAIN>-p6-false/graph.json (heapviz/build.sh, patch
0006, MarkStoreEscaping=false).

Prints:
  - one line per Stava site: program, method:bci, ownership class in graph B, Stava's verdict
  - the cross table of (ownership class, Stava verdict)
  - over the 19 programs of Phase 19 (O07 is counted apart: it exists for library inlining):
    application sites, how many graph N calls HEAP, how many graph B places in a frame (OWN or
    UP), with and without identity returns
"""
import collections
import glob
import json
import os

H = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "build")


def read_own(path):
    own = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if line.startswith("#") or c[1] != "1":
                continue
            parts = c[0].rsplit("|", 2)
            if len(parts) != 3:
                continue
            own[(parts[0], int(parts[1]))] = (c[2], c[5], c[7])   # B class, B up, N class
    return own


def main():
    cross = collections.Counter()
    sites = n_heap = 0
    framed = collections.Counter()
    for d in sorted(glob.glob(os.path.join(H, "own", "*", ""))):
        prog = os.path.basename(os.path.dirname(d))
        base = os.path.join(d, prog + ".own")
        if not os.path.exists(base) or prog == "O07":
            continue
        for suffix in ("", "-id"):
            own = read_own(os.path.join(d, prog + suffix + ".own"))
            if suffix == "":
                sites += len(own)
                n_heap += sum(1 for v in own.values() if v[2] == "HEAP")
            framed["B" + suffix] += sum(1 for v in own.values() if v[0] in ("OWN", "UP"))
            g = os.path.join(H, "out", prog + "-p6-false", "graph.json")
            if suffix or not os.path.exists(g):
                continue
            for n in json.load(open(g, encoding="utf-8"))["sites"]:
                k = (n["method"], n["bci"])
                if n.get("objType") != "site" or k not in own:
                    continue
                o = own[k]
                cls = o[0] + (o[1] if o[0] == "UP" else "")
                cross[(cls, n.get("escapeStatus"))] += 1
                print("%-4s %-42s %-5s Stava %s" % (prog, "%s:%d" % (k[0].split(": ")[-1][:-1], k[1]), cls,
                                                   n.get("escapeStatus")))
    print()
    for k in sorted(cross):
        print("ownership %-5s Stava %-9s %3d sites" % (k[0], k[1], cross[k]))
    print()
    print("19 programs: %d application sites; graph N calls %d HEAP; graph B places %d in a frame, "
          "%d with identity returns" % (sites, n_heap, framed["B"], framed["B-id"]))


if __name__ == "__main__":
    main()
