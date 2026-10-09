#!/usr/bin/env python3
"""dead_end_successors.py - where do successor-pointer chains end without a cause?

    python3 tools/python/dead_end_successors.py <info-dir>

A pointer is recorded only when isEscapingObject(nxt) held, so its target should itself carry
a reason. This counts the pointer targets that carry NONE, by objectType and by whether the
target also appears in .res as escaping, and names the most-pointed-at ones.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from info_to_graph import find_reasons_file, read_reasons, read_via  # noqa: E402


def main():
    d = sys.argv[1]
    rp = find_reasons_file(d, None)
    raw = read_reasons(rp, mode="raw")
    groups = read_via(rp[:-len(".reasons")] + ".via")

    targets = Counter()
    for ptrs in groups.values():
        for t in ptrs:
            targets[t] += 1
    empty = {t: c for t, c in targets.items() if t in raw and not raw[t]}
    missing = {t: c for t, c in targets.items() if t not in raw}
    print("groups %d, distinct pointer targets %d" % (len(groups), len(targets)))
    print("targets with NO reason: %d (%d pointers)" % (len(empty), sum(empty.values())))
    print("   by objectType: %s" % dict(Counter(t[2] for t in empty)))
    print("targets missing from .reasons: %d" % len(missing))
    print("empty groups: %d" % sum(1 for p in groups.values() if not p))
    print("\nmost-pointed-at targets with no reason:")
    for t, c in sorted(empty.items(), key=lambda kv: -kv[1])[:15]:
        print("   %6d  %s <%s,%d>" % (c, t[0], t[2], t[1]))

    # targets whose ONLY reasons are propagated: the cycle / chain case
    prop = {"TRANSITIVE_SUCCESSOR", "PARAM_ESCAPES_VIA_SUCCESSOR"}
    only_prop = [t for t in targets if t in raw and raw[t] and set(raw[t]) <= prop]
    print("\ntargets whose raw reasons are only propagated: %d" % len(only_prop))
    print("   by objectType: %s" % dict(Counter(t[2] for t in only_prop)))


if __name__ == "__main__":
    main()
