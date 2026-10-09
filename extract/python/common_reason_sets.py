#!/usr/bin/env python3
"""
common_reason_sets.py - which reasons, and which exact reason SETS, occur in every benchmark.

WHY SETS AND NOT JUST REASONS
  A reason present in all six benchmarks says only that the construct exists in Java. A reason
  SET present in all six is a recurring escape PATTERN - the same combination of causes landing
  on the same object in six unrelated programs. Those are the clusters worth mapping to source,
  because a pattern that survives six programs is a property of how Java code is written rather
  than of one benchmark.

  This is also the Meet 5 clustering question asked across programs instead of within one:
  Meet 5 asked to cluster objects by their reason multiplicity; the intersection asks which of
  those clusters are universal.

TWO INTERSECTIONS ARE REPORTED
  reasons      element-wise: reasons appearing on >=1 application object in every benchmark.
  reason sets  exact tuples: sets appearing on >=1 application object in every benchmark.

  The second is a subset relationship of the first only in the trivial direction - a common set
  is made of common reasons, but most combinations of common reasons are NOT themselves common.

CAVEAT CARRIED FORWARD
  A reason set that is large and repeated is usually a stamped resolver component
  (Reason-Pipeline-Spec X-A4), not k independent facts about one object. Sets are reported with
  their size so a 6- or 7-element "universal pattern" can be read for what it is.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import find_reasons_file, read_reasons  # noqa: E402


def load(info_dir, prefixes):
    """-> (Counter of exact reason tuples, Counter of individual reasons), app objects only."""
    rp = find_reasons_file(info_dir, None)
    if rp is None:
        raise SystemExit("no .reasons in %s" % info_dir)
    setc, rc = Counter(), Counter()
    for (sig, _bci, _ot), names in read_reasons(rp).items():
        if not names:
            continue
        p = parse_soot_sig(sig)
        if p is None:
            continue
        if not any(p[0].startswith(x) for x in prefixes):
            continue
        setc[tuple(names)] += 1
        for r in names:
            rc[r] += 1
    return setc, rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="append", required=True, metavar="NAME:DIR:PREFIX[,PREFIX]",
                    help="repeatable, e.g. avrora:/tmp/rv/p3out/avrora:avrora.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    per_sets, per_reasons, order = {}, {}, []
    for spec in a.bench:
        name, d, prefs = spec.split(":", 2)
        order.append(name)
        per_sets[name], per_reasons[name] = load(d, prefs.split(","))
        print("   %-8s %6d app objects with reasons, %4d distinct reason sets"
              % (name, sum(per_sets[name].values()), len(per_sets[name])))

    common_r = set.intersection(*(set(per_reasons[n]) for n in order))
    all_r = set().union(*(set(per_reasons[n]) for n in order))
    common_s = set.intersection(*(set(per_sets[n]) for n in order))

    print("\n== reasons in EVERY benchmark: %d of %d seen anywhere"
          % (len(common_r), len(all_r)))
    print("   %-28s %s" % ("reason", "  ".join("%8s" % n for n in order)))
    for r in sorted(common_r, key=lambda k: -sum(per_reasons[n][k] for n in order)):
        print("   %-28s %s" % (r, "  ".join("%8d" % per_reasons[n][r] for n in order)))
    missing = sorted(all_r - common_r)
    if missing:
        print("\n   NOT universal (absent from at least one): %s" % ", ".join(missing))
        for r in missing:
            print("      %-26s %s" % (r, "  ".join("%s=%d" % (n, per_reasons[n][r])
                                                   for n in order)))

    print("\n== exact reason SETS in EVERY benchmark: %d" % len(common_s))
    print("   %-4s %-58s %s" % ("size", "reason set", "  ".join("%8s" % n for n in order)))
    tot = Counter()
    for s in sorted(common_s, key=lambda k: (-sum(per_sets[n][k] for n in order), len(k))):
        label = ",".join(s)
        print("   %-4d %-58s %s"
              % (len(s), label[:58], "  ".join("%8d" % per_sets[n][s] for n in order)))
        for n in order:
            tot[n] += per_sets[n][s]
    print("\n   objects carrying a universal set:")
    for n in order:
        allobj = sum(per_sets[n].values())
        print("      %-8s %6d of %6d  (%.1f%%)"
              % (n, tot[n], allobj, 100.0 * tot[n] / max(1, allobj)))

    out = {"benchmarks": order,
           "commonReasons": sorted(common_r),
           "nonUniversalReasons": missing,
           "commonSets": [{"set": list(s), "size": len(s),
                           "counts": {n: per_sets[n][s] for n in order}}
                          for s in sorted(common_s,
                                          key=lambda k: -sum(per_sets[n][k] for n in order))],
           "coverage": {n: {"universalSetObjects": tot[n],
                            "allObjectsWithReasons": sum(per_sets[n].values())}
                        for n in order}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print("\n   wrote %s" % a.out)


if __name__ == "__main__":
    main()
