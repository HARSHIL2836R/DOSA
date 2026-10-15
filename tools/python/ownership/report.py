#!/usr/bin/env python3
"""report.py - the static ownership tree's numbers, next to Stava's verdict and the fork's walk.

    python3 tools/python/ownership/report.py --bench            six benchmarks, build/own/bench/
    python3 tools/python/ownership/report.py --corpus           every corpus program, build/own/<MAIN>/

POPULATION. For a benchmark, the application allocation sites of Phase 17
(build/out/capture-level/<name>-false-cap50.sites.json): every `new`, `newarray` and
`multianewarray` in a method of the benchmark's own packages, whether or not Spark reaches the
method. Each site carries Stava's verdict under MarkStoreEscaping=false and the fork's walk
level (Micro-Corpus-Log F17.7). The ownership class comes from <dirname>.own, joined on
(method, bci). A site Spark never reaches has no class and is counted as "not in Spark".

CLASSES (design note 2026-09-24-Ownership-Trees.md §5):
    OWN    region is the allocating method: dies no later than the oldest activation of the
           allocating method on its thread returns
    UPk    region is a method k call-graph SCCs above the allocating method
    HEAP   no method dominates the site
"""
import argparse
import collections
import glob
import json
import os
import sys

H = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BENCH = [  # name, .own base name, class prefixes (as tools/scripts/run_all_p6.sh)
    ("avrora", "dacapo", ["avrora."]),
    ("xalan", "xalan", ["org.apache.xalan.", "org.apache.xpath.", "org.apache.xml."]),
    ("luindex", "luindex", ["org.apache.lucene."]),
    ("fop", "fop", ["org.apache.fop."]),
    ("h2", "h2", ["org.h2."]),
    ("pmd", "pmd", ["net.sourceforge.pmd."]),
]


def read_own(path):
    """{(method, bci): (B class, B up, B recursive, N class, B region)}"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            parts = c[0].rsplit("|", 2)
            if len(parts) != 3:      # Spark's placeholders (@NOUNIT:...) name no bci
                continue
            out[(parts[0], int(parts[1]))] = (c[2], int(c[5]), c[6] == "1", c[7], c[3])
    return out


def bucket(cls, up):
    if cls == "UP":
        return "UP%d" % up if 0 <= up < 3 else ("UP3+" if up >= 3 else "UP?")
    return cls


def walk_bucket(w):
    return "heap" if w.startswith("heap") else ("3+" if w.isdigit() and int(w) >= 3 else w)


ORDER = ["OWN", "UP0", "UP1", "UP2", "UP3+", "HEAP", "not in Spark", "UNREACHED"]


def pct(n, d):
    return "%5.1f %%" % (100.0 * n / d) if d else "   -  "


def bench_report(name, base, prefixes, out):
    sites_path = os.path.join(H, "build", "out", "capture-level", "%s-false-cap50.sites.json" % name)
    if not os.path.exists(sites_path):
        print("%s: no Phase 17 site file %s" % (name, sites_path))
        return None
    sites = json.load(open(sites_path))
    res = {"name": name, "sites": len(sites)}
    for tag, suffix in (("B", ""), ("B+id", "-id")):
        p = os.path.join(H, "build", "own", "bench", name, base + suffix + ".own")
        if not os.path.exists(p):
            print("%s: missing %s" % (name, p))
            continue
        own = read_own(p)
        cls = collections.Counter()
        naive = collections.Counter()
        cross_verdict = collections.Counter()
        cross_walk = collections.Counter()
        rec_own = 0
        for m, bci, verdict, walk in sites:
            o = own.get((m, bci))
            if o is None:
                b = "not in Spark"
                nb = b
            else:
                b = bucket(o[0], o[1])
                nb = o[3]
                if o[0] == "OWN" and o[2]:
                    rec_own += 1
            cls[b] += 1
            naive[nb] += 1
            cross_verdict[(b, verdict)] += 1
            cross_walk[(b, walk_bucket(walk))] += 1
        n = len(sites)
        in_spark = n - cls["not in Spark"]
        print("\n== %s, %s: %d application allocation sites, %d in Spark's reachable methods"
              % (name, tag, n, in_spark))
        for k in ORDER:
            if cls[k]:
                print("   %-13s %6d  %s of all  %s of Spark-reached" % (k, cls[k], pct(cls[k], n),
                      pct(cls[k], in_spark) if k != "not in Spark" else "        "))
        print("   OWN in a recursive method: %d" % rec_own)
        print("   graph N (no borrow rule): %s" % dict(naive))
        verdicts = sorted({v for _, v in cross_verdict})
        print("   ownership x Stava verdict:   " + "  ".join("%10s" % v for v in verdicts))
        for k in ORDER:
            if cls[k]:
                print("      %-13s             " % k + "  ".join("%10d" % cross_verdict[(k, v)] for v in verdicts))
        walks = ["0", "1", "2", "3+", "heap"]
        print("   ownership x fork's walk:     " + "  ".join("%7s" % w for w in walks))
        for k in ORDER:
            if cls[k]:
                print("      %-13s             " % k + "  ".join("%7d" % cross_walk[(k, w)] for w in walks))
        why_path = p.replace(".own", ".ownwhy")
        if os.path.exists(why_path):
            kinds, details = collections.Counter(), collections.Counter()
            popset = {(m, bci) for m, bci, _, _ in sites}
            for line in open(why_path, encoding="utf-8"):
                c = line.rstrip("\n").split("\t")
                parts = c[0].rsplit("|", 2)
                if line.startswith("#") or len(parts) != 3 or (parts[0], int(parts[1])) not in popset:
                    continue
                kinds[c[1]] += 1
                details[c[1] + ":" + c[2]] += 1
            print("   why HEAP: %s" % dict(kinds.most_common()))
            for k, v in details.most_common(4):
                print("      %5d  %s" % (v, k[:150]))
        res[tag] = {"classes": dict(cls), "naive": dict(naive), "recursive_own": rec_own,
                    "x_verdict": {"%s|%s" % k: v for k, v in cross_verdict.items()},
                    "x_walk": {"%s|%s" % k: v for k, v in cross_walk.items()}}
    return res


def whatif_report():
    """build/own/whatif/<name>/<base>-id.ownwhatif over Phase 17's population: how many sites the
    what-if variants (S: Spark's special nodes keep no fields; P: phantom callees keep nothing;
    SP: both) move out of HEAP. Not sound; a measure of how much HEAP each source accounts for."""
    print("what-if (identity returns on), Phase 17 application sites in Spark's reach:")
    print("   %-8s %8s %8s %8s %8s   %s" % ("", "B HEAP", "S HEAP", "P HEAP", "SP HEAP", "SP: HEAP to OWN/UP"))
    for name, base, _p in BENCH:
        p = os.path.join(H, "build", "own", "whatif", name, base + "-id.ownwhatif")
        sp = os.path.join(H, "build", "out", "capture-level", "%s-false-cap50.sites.json" % name)
        if not os.path.exists(p) or not os.path.exists(sp):
            continue
        pop = {(m, bci) for m, bci, _v, _w in json.load(open(sp))}
        heap = collections.Counter()
        moved = 0
        for line in open(p, encoding="utf-8"):
            c = line.rstrip("\n").split("\t")
            parts = c[0].rsplit("|", 2)
            if line.startswith("#") or len(parts) != 3 or (parts[0], int(parts[1])) not in pop:
                continue
            for tag, col in (("B", 2), ("S", 4), ("P", 6), ("SP", 8)):
                if c[col] == "HEAP":
                    heap[tag] += 1
            if c[2] == "HEAP" and c[8] in ("OWN", "UP"):
                moved += 1
        print("   %-8s %8d %8d %8d %8d   %d" % (name, heap["B"], heap["S"], heap["P"], heap["SP"], moved))


def corpus_report():
    for d in sorted(glob.glob(os.path.join(H, "build", "own", "*", ""))):
        prog = os.path.basename(os.path.dirname(d))
        if prog == "bench":
            continue
        for suffix in ("", "-id"):
            p = os.path.join(d, prog + suffix + ".own")
            if not os.path.exists(p):
                continue
            rows = []
            with open(p, encoding="utf-8") as f:
                for line in f:
                    c = line.rstrip("\n").split("\t")
                    if line.startswith("#") or c[1] != "1":
                        continue
                    region = c[3].split(": ")[-1].rstrip(">") if c[3].startswith("<") else c[3]
                    rows.append("%s %s@%s" % (c[0].split(": ")[-1].split(">")[0] + ":" + c[0].rsplit("|", 2)[1],
                                              bucket(c[2], int(c[5])), region))
            print("%-4s %-3s %s" % (prog, suffix or "B", "; ".join(rows)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--whatif", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", default=None)
    ap.add_argument("--brief", action="store_true",
                    help="with --bench: one line per benchmark, the table of Micro-Corpus-Log F20.4")
    a = ap.parse_args()
    if a.corpus:
        corpus_report()
    if a.whatif:
        whatif_report()
    if a.bench:
        out = sys.stdout
        if a.brief:
            sys.stdout = open(os.devnull, "w")
        allres = []
        for name, base, prefixes in BENCH:
            if a.only and name not in a.only:
                continue
            r = bench_report(name, base, prefixes, sys.stdout)
            if r:
                allres.append(r)
        if a.json:
            json.dump(allres, open(a.json, "w", encoding="utf-8", newline="\n"), indent=1)
        if a.brief:
            sys.stdout = out
            print("%-8s %6s %8s %14s %4s %6s %12s %9s %12s %14s" % (
                "", "sites", "in Spark", "OWN (B+id)", "UP", "HEAP", "OWN, no id", "N OWN", "OWN walk 0", "OWN recursive"))
            for r in allres:
                c, c0 = r["B+id"]["classes"], r["B"]["classes"]
                insp = r["sites"] - c.get("not in Spark", 0)
                up = sum(v for k, v in c.items() if k.startswith("UP"))
                print("%-8s %6d %8d %6d (%4.1f %%) %4d %6d %12d %9d %12d %14d" % (
                    r["name"], r["sites"], insp, c.get("OWN", 0), 100.0 * c.get("OWN", 0) / max(1, insp), up,
                    c.get("HEAP", 0), c0.get("OWN", 0), r["B+id"]["naive"].get("OWN", 0),
                    r["B+id"]["x_walk"].get("OWN|0", 0), r["B+id"]["recursive_own"]))


if __name__ == "__main__":
    main()
