#!/usr/bin/env python3
"""scan_figures.py - does any current figure DRAW a propagated reason or a placeholder?

    python3 tools/python/scan_figures.py render/figures '*-p4-*'

Captions legitimately name TRANSITIVE_SUCCESSOR and PARAM_ESCAPES_VIA_SUCCESSOR ("replaced by
the nearest causes..."), so a plain grep flags every file. This looks only where data is drawn:
cluster node labels and table cells in the .dot files, and the reasonsets payload of an explorer.
"""
import fnmatch
import json
import os
import re
import sys

PROP = ("TRANSITIVE_SUCCESSOR", "PARAM_ESCAPES_VIA_SUCCESSOR")


def main(args=None):
    d, pat = args[0], args[1] if len(args) > 2 else "*"
    bad, seen = [], 0
    for name in sorted(os.listdir(d)):
        if not fnmatch.fnmatch(name, pat):
            continue
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            continue
        s = open(path, encoding="utf-8", errors="replace").read()
        if name.endswith(".dot"):
            seen += 1
            drawn = " ".join(re.findall(r'c\d+ \[label="(.*?)"', s) + re.findall(r"<TD>(.*?)</TD>", s))
            for p in PROP:
                if p in drawn:
                    bad.append((name, "draws " + p))
            if "None reasons" in drawn:
                bad.append((name, "'None reasons' label"))
            if "Reasons: ?" in s:
                bad.append((name, "'Reasons: ?' caption"))
        elif name.endswith(".svg"):
            seen += 1
            if "Reasons: ?" in s:
                bad.append((name, "'Reasons: ?' caption"))
        elif name.endswith(".html"):
            seen += 1
            m = re.search(r'"reasonsets":(\[\[.*?\]\]|\[\])', s)
            if not m:
                bad.append((name, "no reasonsets payload found"))
                continue
            sets = json.loads(m.group(1))
            for p in PROP:
                if any(p in rs for rs in sets):
                    bad.append((name, "reason set contains " + p))
    print("scanned %d files matching %s" % (seen, pat))
    for n, why in bad:
        print("   %s: %s" % (n, why))
    print("   clean" if not bad else "   %d problems" % len(bad))
    return (1 if bad else 0)


if __name__ == "__main__":
    main()
