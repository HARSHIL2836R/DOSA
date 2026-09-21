#!/usr/bin/env python3
"""own_witness.py - does the own/inherited split of patch 0005 agree with the bytecode?

    python3 tools/own_witness.py --info-dir DIR --classes CLASSDIR --class-prefix avrora. \
        [--java-home JDK]

A reason with a single visible opcode (MONITOR -> monitorenter, THROWN -> athrow,
STATIC_FIELD_STORE -> putstatic, STATIC_FIELD_LOAD -> getstatic, CONSTANT_OBJECT -> ldc*) can
only have fired in a method that contains that opcode. So:

  own reason, opcode ABSENT from the object's method   -> the split is WRONG (expect 0)
  inherited reason, opcode absent                     -> consistent, and the case the audit
                                                         could see (Viz-Faithfulness-Audit 4.2)
  inherited reason, opcode present                    -> consistent; the opcode exists but
                                                         fired on a different object

Raw reasons, because a root cause resolved through a pointer fired in another method. Every
application object is checked, all object types.
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import find_reasons_file, read_reasons  # noqa: E402
from reason_source_map import WITNESS, Bytecode  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--classes", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--java-home", default=os.environ.get("JAVA_HOME", ""))
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()

    rp = find_reasons_file(a.info_dir, None)
    reasons = read_reasons(rp, mode="raw")
    if reasons.own is None:
        raise SystemExit("%s has no own-reason columns (run predates patch 0005)" % rp)
    bc = Bytecode(a.classes, a.java_home)

    tally = Counter()
    wrong = []
    objects = 0
    for key, names in reasons.items():
        sig, bci, objtype = key
        p = parse_soot_sig(sig)
        if p is None or not any(p[0].startswith(x) for x in a.class_prefix):
            continue
        own = set(reasons.own.get(key, ()))
        checked = [r for r in names if r in WITNESS]
        if not checked:
            continue
        objects += 1
        cls, mname, _ = p
        for r in checked:
            offs = bc.offsets(cls, mname, WITNESS[r])
            side = "own" if r in own else "inherited"
            if offs is None:
                tally[(r, side, "method not found")] += 1
            elif offs:
                tally[(r, side, "opcode present")] += 1
            else:
                tally[(r, side, "opcode ABSENT")] += 1
                if side == "own":
                    wrong.append((sig, bci, objtype, r))

    print("== own/inherited split vs bytecode, %d application objects carrying a witnessable reason"
          % objects)
    print("   %-20s %-10s %8s %8s %8s" % ("reason", "side", "present", "ABSENT", "no method"))
    for r in WITNESS:
        for side in ("own", "inherited"):
            row = [tally[(r, side, k)] for k in ("opcode present", "opcode ABSENT",
                                                  "method not found")]
            if any(row):
                print("   %-20s %-10s %8d %8d %8d" % (r, side, *row))
    print("\n   own reasons with the opcode absent from their method: %d  %s"
          % (len(wrong), "<- PASS" if not wrong else "<- FAIL"))
    for w in wrong[:a.show]:
        print("      %s <%s,%s> %s" % (w[0], w[2], w[1], w[3]))
    if bc.missing:
        print("   classes javap could not read: %d" % len(bc.missing))
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
