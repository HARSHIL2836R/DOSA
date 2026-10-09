#!/usr/bin/env python3
"""roots_effect.py - what resolving propagated reasons to their causes does to the numbers.

    python3 tools/python/roots_effect.py <info-dir> <label> [class-prefix ...]

Reads one patch-0004 .reasons twice, raw and roots, over internal + external objects (the
reported population), optionally restricted to application classes, and prints:
  * the multiplicity histogram both ways,
  * single-reason attribution both ways,
  * what the objects whose ONLY raw reason was propagated resolved to.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import (REASONS_PROPAGATED, find_reasons_file,  # noqa: E402
                           read_reasons)

COUNTED = ("internal", "external")


def main():
    d, label, prefixes = sys.argv[1], sys.argv[2], sys.argv[3:]
    rp = find_reasons_file(d, None)
    if rp is None:
        raise SystemExit("no .reasons in %s" % d)
    raw = read_reasons(rp, mode="raw")
    roots = read_reasons(rp, mode="roots")

    def keep(k):
        if k[2] not in COUNTED:
            return False
        if not prefixes:
            return True
        p = parse_soot_sig(k[0])
        return p is not None and any(p[0].startswith(x) for x in prefixes)

    keys = [k for k in raw if keep(k)]
    prop = set(REASONS_PROPAGATED)
    print("== %s   %d objects (%s)%s" % (label, len(keys), "+".join(COUNTED),
                                        ", prefixes " + " ".join(prefixes) if prefixes else ""))

    for name, m in (("raw", raw), ("roots", roots)):
        h = Counter(len(m[k]) for k in keys)
        print("   %-5s reasonCount: %s" % (name, "  ".join("%d:%d" % (c, h[c]) for c in sorted(h))))

    for name, m in (("raw", raw), ("roots", roots)):
        single = Counter(m[k][0] for k in keys if len(m[k]) == 1)
        print("\n   single-reason attribution, %s (%d objects)" % (name, sum(single.values())))
        for r, c in single.most_common():
            print("      %-28s %6d" % (r, c))

    only_prop = [k for k in keys if raw[k] and set(raw[k]) <= prop]
    became = Counter(tuple(roots[k]) for k in only_prop)
    print("\n   objects whose raw set was ONLY propagated: %d; resolved to %d distinct sets"
          % (len(only_prop), len(became)))
    for s, c in became.most_common(15):
        print("      %6d  %s" % (c, ", ".join(s)))

    mixed = [k for k in keys if set(raw[k]) & prop and set(raw[k]) - prop]
    grew = sum(1 for k in mixed if len(roots[k]) > len(raw[k]))
    same = sum(1 for k in mixed if len(roots[k]) == len(raw[k]))
    shrank = sum(1 for k in mixed if len(roots[k]) < len(raw[k]))
    absorbed = sum(1 for k in mixed if set(roots[k]) == set(raw[k]) - prop)
    print("\n   objects with a propagated AND a direct reason: %d" % len(mixed))
    print("      propagated reason added nothing new (double count removed): %d" % absorbed)
    print("      count grew %d, same %d, shrank %d" % (grew, same, shrank))


if __name__ == "__main__":
    main()
