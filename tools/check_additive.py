#!/usr/bin/env python3
"""
check_additive.py — constraint 3, mechanically.

"`graph.json` stays the interface. Reason data enters as ADDITIVE fields on existing object
nodes." and "Additive fields only; if a change would alter any existing field, stop and say so."

This compares a graph.json produced BEFORE the instrumentation against one produced after, and
fails if anything other than the four new node keys and the one new meta key differs. It is the
only way to make that constraint a check rather than a claim: the micro-corpus path is verified
against eight hand-derivations and a silent change to an existing field would invalidate all of
them at once.

  python3 tools/check_additive.py --before build/graphjson-preinstrument \\
                                 --after  build/out --suffix graph.json
"""

import argparse
import json
import os
import sys

NEW_NODE_KEYS = {"escapeReasons", "reasonCount", "realReasonCount", "surrenderReasonCount",
                 "ownReasons", "inheritedReasons"}   # the last two since patch 0005
NEW_META_KEYS = {"reasons"}


def strip_new(g):
    """A copy of g with the Phase 11 additions removed, for comparison against the before."""
    out = {"meta": {k: v for k, v in g["meta"].items() if k not in NEW_META_KEYS},
           "nodes": [{k: v for k, v in n.items() if k not in NEW_NODE_KEYS}
                     for n in g["nodes"]],
           "edges": g["edges"]}
    for k, v in g.items():
        if k not in ("meta", "nodes", "edges"):
            out[k] = v
    return out


def diff(before, after, name, problems):
    b, a = strip_new(before), strip_new(after)
    if b["meta"] != a["meta"]:
        for k in sorted(set(b["meta"]) | set(a["meta"])):
            if b["meta"].get(k) != a["meta"].get(k):
                problems.append("%s: meta[%r] %r -> %r"
                                % (name, k, b["meta"].get(k), a["meta"].get(k)))
    bn = {n["id"]: n for n in b["nodes"]}
    an = {n["id"]: n for n in a["nodes"]}
    for i in sorted(set(bn) - set(an)):
        problems.append("%s: node vanished: %s" % (name, i))
    for i in sorted(set(an) - set(bn)):
        problems.append("%s: node appeared: %s" % (name, i))
    for i in sorted(set(bn) & set(an)):
        for k in sorted(set(bn[i]) | set(an[i])):
            if bn[i].get(k) != an[i].get(k):
                problems.append("%s: node %s field %r: %r -> %r"
                                % (name, i, k, bn[i].get(k), an[i].get(k)))
    if b["edges"] != a["edges"]:
        problems.append("%s: edge list differs (%d -> %d edges)"
                        % (name, len(b["edges"]), len(a["edges"])))
    # and the additions must actually be there and internally consistent
    for n in after["nodes"]:
        if n["kind"] == "sink":
            if NEW_NODE_KEYS & set(n):
                problems.append("%s: sink %s was stamped with reason fields" % (name, n["id"]))
            continue
        if not NEW_NODE_KEYS <= set(n):
            problems.append("%s: node %s is missing reason fields" % (name, n["id"]))
            continue
        if n["reasonCount"] != len(n["escapeReasons"]):
            problems.append("%s: node %s reasonCount %d != len(escapeReasons) %d"
                            % (name, n["id"], n["reasonCount"], len(n["escapeReasons"])))
        if n["realReasonCount"] + n["surrenderReasonCount"] != n["reasonCount"]:
            problems.append("%s: node %s real+surrender != reasonCount" % (name, n["id"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="dir of <PROG>-<cfg>.json snapshots")
    ap.add_argument("--after", required=True, help="build/out")
    ap.add_argument("--suffix", default="graph.json")
    a = ap.parse_args()

    problems, checked = [], 0
    for fn in sorted(os.listdir(a.before)):
        if not fn.endswith(".json"):
            continue
        name = fn[:-len(".json")]
        after_path = os.path.join(a.after, name, a.suffix)
        if not os.path.exists(after_path):
            problems.append("%s: no %s in %s" % (name, a.suffix, after_path))
            continue
        with open(os.path.join(a.before, fn), encoding="utf-8") as fh:
            before = json.load(fh)
        with open(after_path, encoding="utf-8") as fh:
            after = json.load(fh)
        diff(before, after, name, problems)
        checked += 1

    print("compared %d graph.json pairs" % checked)
    if problems:
        print("NOT ADDITIVE - %d problems:" % len(problems))
        for p in problems[:80]:
            print("  " + p)
        if len(problems) > 80:
            print("  ... and %d more" % (len(problems) - 80))
        sys.exit(1)
    print("ADDITIVE: every pre-existing meta key, node, node field and edge is unchanged; "
          "the only differences are the four new node keys and meta.reasons.")


if __name__ == "__main__":
    main()
