#!/usr/bin/env python3
"""
audit_instrumentation.py - is every escape-introducing site instrumented?

THE QUESTION THIS ANSWERS
  RETURNED was invisible for eleven phases. Two independent mechanisms hid it, and both are
  now understood. The question that matters is whether anything ELSE is hidden the same way.
  Reason-Pipeline-Spec X-A1 says the site census was "a grep over three patterns; anything
  reaching Escape by another route is a silent zero and nothing detects it." This is that
  detector.

  It finds every statement in the analysis that can put Escape into an EscapeStatus, and
  checks whether an EscapeReasons.record() call sits within WINDOW lines of it. A site with no
  nearby record is a candidate for a reason that fires and is never attributed.

WHAT COUNTS AS AN ESCAPE-INTRODUCING SITE
  setEscape()                          -> purgeAndEscape(), status becomes {Escape}
  purgeAndEscape()                     -> same, called directly
  new EscapeStatus(Escape.getInstance())  a fresh escaping status
  SetComponent(comp, Escape...)        -> the resolver escaping a whole component

  Commented-out lines are ignored. es/EscapeStatus.java and es/Escape.java are the lattice
  itself rather than call sites, and are skipped.

WHAT A CLEAN RESULT DOES NOT PROVE
  Proximity is a proxy for attribution, not a proof of it: a record() on the wrong object, or
  guarded by a condition the escape is not, still counts as covered here. And a site reached
  only on a path this build never takes is reported as uncovered whether or not that matters.
  The complementary runtime check is the Escape-with-no-reason count, which is a fact about a
  real run rather than about the text.
"""
import argparse
import os
import re
import sys

SITE = re.compile(r"(setEscape\s*\(\)|purgeAndEscape\s*\(\)"
                  r"|new\s+EscapeStatus\s*\(\s*Escape\.getInstance"
                  r"|SetComponent\s*\([^)]*(?<!No)Escape\.getInstance)")
RECORD = re.compile(r"EscapeReasons\s*\.\s*record\s*\(")
SKIP_FILES = ("es/EscapeStatus.java", "es/Escape.java", "es/EscapeReason.java",
              "es/EscapeReasons.java")


def is_comment(line):
    s = line.strip()
    return s.startswith("//") or s.startswith("*") or s.startswith("/*")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="instrumented stava source tree")
    ap.add_argument("--window", type=int, default=12,
                    help="lines either side searched for a record() call")
    ap.add_argument("--known", default=None,
                    help="json of sites covered by a mechanism proximity cannot see, each "
                         "with a justification. A site that is neither proximate nor listed "
                         "here is a real finding and exits non-zero.")
    a = ap.parse_args()

    known = {}
    if a.known:
        import json
        for e in json.load(open(a.known, encoding="utf-8"))["sites"]:
            known[(e["file"], e["line"])] = e["why"]

    covered, uncovered, by_mech = [], [], []
    for root, _dirs, fns in os.walk(a.src):
        for fn in sorted(fns):
            if not fn.endswith(".java"):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, a.src).replace(os.sep, "/")
            if any(rel.endswith(s) for s in SKIP_FILES):
                continue
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
            for i, line in enumerate(lines):
                if is_comment(line) or not SITE.search(line):
                    continue
                lo, hi = max(0, i - a.window), min(len(lines), i + a.window + 1)
                near = any(RECORD.search(lines[j]) and not is_comment(lines[j])
                           for j in range(lo, hi))
                entry = (rel, i + 1, line.strip()[:88])
                if near:
                    covered.append(entry)
                elif (rel, i + 1) in known:
                    by_mech.append(entry + (known[(rel, i + 1)],))
                else:
                    uncovered.append(entry)

    print("== escape-introducing sites in %s" % a.src)
    print("   window: +/-%d lines\n" % a.window)
    print("   COVERED (a record() call is nearby): %d" % len(covered))
    for rel, ln, txt in covered:
        print("      %-46s %5d  %s" % (rel, ln, txt))
    print("\n   COVERED BY A NON-PROXIMATE MECHANISM (justified in --known): %d"
          % len(by_mech))
    for rel, ln, txt, why in by_mech:
        print("      %-46s %5d  %s" % (rel, ln, txt))
        print("            %s" % why)

    print("\n   UNCOVERED - no record(), no justification: %d" % len(uncovered))
    for rel, ln, txt in uncovered:
        print("      %-46s %5d  %s" % (rel, ln, txt))

    total = len(covered) + len(by_mech) + len(uncovered)
    print("\n   %d proximate + %d justified = %d of %d sites accounted for (%.0f%%)"
          % (len(covered), len(by_mech), len(covered) + len(by_mech), total,
             100.0 * (len(covered) + len(by_mech)) / max(1, total)))
    if uncovered:
        print("   ^ each of these is a candidate for a reason that fires and is never "
              "attributed, which is how RETURNED stayed invisible for eleven phases.")
    return 1 if uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
