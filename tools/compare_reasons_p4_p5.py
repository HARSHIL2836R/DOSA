#!/usr/bin/env python3
"""compare_reasons_p4_p5.py - patch 0005 must add columns 6-7 and change nothing else.

    python3 tools/compare_reasons_p4_p5.py <p4 dir> <p5 dir> <dirname>

Checks, printed as one line:
  cols      every line has 7 fields
  c1-4      columns 1-4 identical as a multiset
  via       column 5's pointer SET per object identical (group numbers may shift, because own
            groups now take numbers in the same sequence)
  subset    own (column 6) is a subset of all (column 4) on every line
  inherited objects whose own is a strict subset of all
Exit 1 on any failure.
"""
import sys


def load(d, name):
    via = {}
    for line in open("%s/%s.via" % (d, name), encoding="utf-8"):
        g, _, ptrs = line.rstrip("\n").partition("\t")
        via[g] = frozenset(p for p in ptrs.split(";") if p)
    rows = []
    for line in open("%s/%s.reasons" % (d, name), encoding="utf-8"):
        rows.append(line.rstrip("\n").split("\t"))
    return rows, via


def main():
    p4, p5, name = sys.argv[1:4]
    r4, v4 = load(p4, name)
    r5, v5 = load(p5, name)
    bad = []
    cols = sorted({len(r) for r in r5})
    if cols != [7]:
        bad.append("columns %s" % cols)
    if sorted("\t".join(r[:4]) for r in r4) != sorted("\t".join(r[:4]) for r in r5):
        bad.append("columns 1-4 differ")
    deref4 = sorted(("\t".join(r[:3]), v4.get(r[4], frozenset()) if r[4] else None) for r in r4)
    deref5 = sorted(("\t".join(r[:3]), v5.get(r[4], frozenset()) if r[4] else None) for r in r5)
    nvia = sum(1 for a, b in zip(deref4, deref5) if a != b) + abs(len(deref4) - len(deref5))
    if nvia:
        bad.append("column-5 pointer sets differ on %d objects" % nvia)
    notsub = inh = own_ptr = 0
    for r in r5:
        a = set(x for x in r[3].split(",") if x)
        o = set(x for x in r[5].split(",") if x)
        if not o <= a:
            notsub += 1
        if o < a:
            inh += 1
        if r[6]:
            own_ptr += 1
    if notsub:
        bad.append("own not a subset of all on %d lines" % notsub)
    print("%-4s lines %6d  cols %s  c1-4 %s  via %s  subset %s  inherited %5d  own-pointer %5d  %s"
          % (name, len(r5), cols, "ok" if "columns 1-4 differ" not in bad else "DIFF",
             "ok" if not nvia else nvia, "ok" if not notsub else notsub, inh, own_ptr,
             "PASS" if not bad else "FAIL: " + "; ".join(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
