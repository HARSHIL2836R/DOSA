#!/usr/bin/env python3
"""p4_summary.py - per-benchmark headline numbers for the patch-0004 roots-mode figures.

    python3 tools/p4_summary.py

Reads /tmp/rv/p4info/<bench>-<cfg>. Population = internal + external in application classes,
exactly as the figures take it. For each run: single-reason share of objects with a reason, the
top single reason, the largest reason-set cluster, and how the SUCCESSOR_* gap constants fall -
in particular what share of them sit in ONE successor-pointer group (a component stamp).
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from benchmark_scale import build  # noqa: E402
from info_to_graph import REASONS_GAP, find_reasons_file, read_reasons  # noqa: E402

RUNS = [("avrora", "false", ["avrora."]), ("avrora", "true", ["avrora."]),
        ("xalan", "false", ["org.apache.xalan.", "org.apache.xpath.", "org.apache.xml."]),
        ("luindex", "false", ["org.apache.lucene."]), ("fop", "false", ["org.apache.fop."]),
        ("h2", "false", ["org.h2."]), ("pmd", "false", ["net.sourceforge.pmd."])]


def main():
    rows = []
    for name, cfg, pre in RUNS:
        d = "/tmp/rv/p4info/%s-%s" % (name, cfg)
        rp = find_reasons_file(d, None)
        raw = read_reasons(rp, mode="raw")
        roots = read_reasons(rp, mode="roots")
        group = {}
        for line in open(rp, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 5 and p[4]:
                group[(p[0], int(p[1]), p[2])] = int(p[4])
        nodes, _h, _d, _f = build(d, pre, None)
        pop = [(n["method"], int(n["bci"]), n["objType"]) for n in nodes.values()
               if n["kind"] == "object"]
        withr = [k for k in pop if roots.get(k)]
        single = Counter(roots[k][0] for k in withr if len(roots[k]) == 1)
        rsingle = sum(1 for k in pop if len(raw.get(k, [])) == 1)
        sets = Counter(tuple(roots[k]) for k in withr)
        big_set, big_n = sets.most_common(1)[0]
        gap = [k for k in withr if set(roots[k]) & set(REASONS_GAP)]
        gg = Counter(group.get(k) for k in gap)
        top_g = gg.most_common(1)[0][1] if gg else 0
        rows.append((name, cfg, len(pop), len(withr), rsingle, sum(single.values()),
                     single.most_common(1)[0], (len(big_set), big_n), len(gap), top_g))

    print("%-8s %-5s %6s %6s %13s %13s  %-34s %-14s %s"
          % ("bench", "cfg", "objs", "escape", "single raw", "single roots", "top single (roots)",
             "largest set", "gap objs (in one group)"))
    for (n, c, p, w, rs, s, top, big, g, tg) in rows:
        print("%-8s %-5s %6d %6d %6d %5.1f%% %6d %5.1f%%  %-26s %6d  %2d r x %-6d %d (%d)"
              % (n, c, p, w, rs, 100.0 * rs / w, s, 100.0 * s / w, top[0], top[1],
                 big[0], big[1], g, tg))


if __name__ == "__main__":
    main()
