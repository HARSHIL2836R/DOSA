#!/usr/bin/env python3
"""escape_no_reason.py - application objects Stava resolves to Escape with no reason recorded
(objective O3 of the viz audit), with what the summaries say about them.

    python3 tools/python/escape_no_reason.py --run-dir /tmp/rv/p6out/xalan-false \
        --info-dir /tmp/rv/p6info/xalan-false --class-prefix org.apache.xalan. ...
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "extract", "python"))
from benchmark_scale import build  # noqa: E402
from capture_level import load  # noqa: E402
from info_to_graph import find_reasons_file, read_reasons  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--class-prefix", required=True, nargs="+")
    a = ap.parse_args()
    raw = read_reasons(find_reasons_file(a.info_dir, None), mode="raw")
    nodes, _h, _d, _f = build(a.info_dir, a.class_prefix, None)
    pre, _fields, _ret = load(a.run_dir)
    for n in sorted(nodes.values(), key=lambda n: n["id"]):
        if n["kind"] != "object":
            continue
        st = (n.get("escapeStatus") or "").split(",")
        key = (n["method"], int(n["bci"]), n["objType"])
        if "Escape" in st and not raw.get(key):
            o = (n["objType"], int(n["bci"]))
            print("%s %s:%s" % (n["method"], n["objType"], n["bci"]))
            print("    pre-resolution states: %s" % (pre.get(n["method"], {}).get(o),))


if __name__ == "__main__":
    main()
