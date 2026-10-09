#!/usr/bin/env python3
"""
hidden_reason_check.py - four detectors for "is another reason hidden the way RETURNED was?"

RETURNED was invisible for eleven phases. Reconstructing how, there were four distinguishable
ways a reason can be present in the enum and absent from every number we report. Each has a
signature that can be checked mechanically, and each is checked here.

  D1  NEVER FIRES AT ALL
      The constant is declared and no object in any benchmark carries it. Either the site is
      unreachable in these programs, or the site is never recorded, or the constant is dead.
      Indistinguishable from the data alone - but it names the exact set worth reading the
      Java for, which is a much smaller job than auditing everything.

  D2  CONFINED TO AN EXCLUDED ObjectType   <- this is what hid RETURNED
      The reason only ever lands on parameter / returnValue / argument nodes, and every
      reported statistic runs over internal + external (Reason-Pipeline-Spec X-D1). The reason
      fires thousands of times and appears in no figure.

  D3  NEVER CO-OCCURS   <- this is the OTHER thing that hid RETURNED
      The reason appears in exactly one distinct reason set, namely {itself}. For a genuinely
      independent property that is astronomically unlikely across six programs. It is the
      fingerprint of the lattice destroying the reason whenever a second one is present
      (X-A2): EscapeStatus.purge() deletes a conditional value the moment the object already
      escapes, so the reason survives only when it is the sole cause.

  D4  ESCAPES WITH NO REASON AT ALL
      Objects the analysis resolved to Escape that carry an empty reason set. Every one is
      either a firing site that was never instrumented, or an attribution lost after the fact.
      This is the only detector that finds a reason nobody has thought of, because it does not
      depend on knowing what to look for. It needs the .info files, so it is reported by
      tools/python/check_invariant.py rather than here.

WHAT THIS CANNOT DO
  D1-D3 all start from the enum. A firing site with no constant at all is invisible to every
  one of them; only D4 and the static audit (tools/python/audit_instrumentation.py) can see that.
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import (REASON_ORDER, SURRENDER, find_reasons_file,  # noqa: E402
                           read_reasons)

COUNTED_TYPES = ("internal", "external")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="append", required=True,
                    metavar="NAME:DIR:PREFIX[,PREFIX]")
    ap.add_argument("--app-only", action="store_true",
                    help="restrict to --class-prefix classes; off by default because a "
                         "reason hidden in the JDK half is still hidden")
    a = ap.parse_args()

    seen_anywhere = Counter()
    per_type = defaultdict(Counter)
    sets_with = defaultdict(set)
    names = []

    for spec in a.bench:
        name, d, prefs = spec.split(":", 2)
        names.append(name)
        prefixes = prefs.split(",")
        rp = find_reasons_file(d, None)
        if rp is None:
            raise SystemExit("no .reasons in %s" % d)
        for (sig, _bci, objtype), rs in read_reasons(rp, mode="raw").items():  # audits Stava's own constants
            if not rs:
                continue
            if a.app_only:
                p = parse_soot_sig(sig)
                if p is None or not any(p[0].startswith(x) for x in prefixes):
                    continue
            key = tuple(rs)
            for r in rs:
                seen_anywhere[r] += 1
                per_type[r][objtype] += 1
                sets_with[r].add(key)

    declared = sorted(REASON_ORDER, key=lambda k: REASON_ORDER[k])
    print("== hidden-reason check over %s%s"
          % (", ".join(names), " (application only)" if a.app_only else " (whole run)"))
    print("   %d constants declared, %d fire at least once\n"
          % (len(declared), sum(1 for r in declared if seen_anywhere[r])))

    d1 = [r for r in declared if not seen_anywhere[r]]
    print("   D1  NEVER FIRES ANYWHERE: %d" % len(d1))
    for r in d1:
        print("       %-30s %s" % (r, "surrender" if r in SURRENDER else "real"))
    if d1:
        print("       ^ read the Java for these. Either the site cannot be reached by these")
        print("         programs, or it is never recorded, and the data cannot tell you which.")

    d2 = [r for r in declared
          if seen_anywhere[r] and not any(per_type[r][t] for t in COUNTED_TYPES)]
    print("\n   D2  FIRES, BUT NEVER ON A COUNTED ObjectType: %d" % len(d2))
    for r in d2:
        print("       %-30s %d objects, only on %s"
              % (r, seen_anywhere[r],
                 ", ".join(sorted(t for t in per_type[r] if per_type[r][t]))))
    if d2:
        print("       ^ invisible in every reported figure while firing this often. This is")
        print("         exactly how RETURNED was hidden until patch 0003.")

    d3 = [r for r in declared
          if seen_anywhere[r] and sets_with[r] == {(r,)}]
    print("\n   D3  NEVER CO-OCCURS (only distinct set is {itself}): %d" % len(d3))
    for r in d3:
        print("       %-30s %d objects, 1 distinct reason set" % (r, seen_anywhere[r]))
    if d3:
        print("       ^ the purge() fingerprint (X-A2): the reason is destroyed whenever a")
        print("         second one is present, so multiplicity can never exceed one.")

    print("\n   -- every constant, for reference")
    print("   %-30s %9s %8s %8s %8s %8s %6s"
          % ("reason", "objects", "internal", "external", "param", "returnV", "sets"))
    for r in declared:
        if not seen_anywhere[r]:
            continue
        c = per_type[r]
        print("   %-30s %9d %8d %8d %8d %8d %6d"
              % (r, seen_anywhere[r], c["internal"], c["external"],
                 c["parameter"], c["returnValue"], len(sets_with[r])))

    bad = len(d2) + len(d3)
    print("\n   D2+D3 findings: %d" % bad)
    print("   D4 (Escape with an empty reason set) is a different detector and needs the")
    print("   .info files: run tools/python/check_invariant.py. It is the only one that can find a")
    print("   reason nobody has named yet.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
