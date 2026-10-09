#!/usr/bin/env python3
"""check_invariant.py - the two-way invariant the integrity checks rest on.

  non-empty reason set  =>  Escape
  Escape                =>  non-empty reason set

Patch 0003 records RETURNED at setAsReturn, during the intraprocedural pass, before the
resolver runs. If any object could be recorded there and still resolve to NoEscape, the first
half breaks. Run this on the before and after trees and compare.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons


def check(d, label):
    rp = find_reasons_file(d, None)
    if rp is None:
        print("%-22s no .reasons" % label)
        return
    nodes, _he, _de, _f = build(d, [""], read_reasons(rp))
    bad_ne, bad_esc, tot_esc = [], 0, 0
    for n in nodes.values():
        st = n.get("escapeStatus")
        if not st:
            continue
        toks = [t.strip() for t in st.split(",")]
        rs = n.get("escapeReasons") or []
        if "Escape" in toks:
            tot_esc += 1
            if not rs:
                bad_esc += 1
        elif "NoEscape" in toks and rs:
            bad_ne.append((n["method"], n["bci"], n["objType"], rs))
    print("%-22s Escape=%-6d  NoEscape-with-reasons=%-4d  Escape-with-none=%d"
          % (label, tot_esc, len(bad_ne), bad_esc))
    for m, b, t, rs in bad_ne[:4]:
        print("      %s <%s,%s> %s" % (m, t, b, ",".join(rs)))


if __name__ == "__main__":
    for i in range(1, len(sys.argv), 2):
        check(sys.argv[i], sys.argv[i + 1])
