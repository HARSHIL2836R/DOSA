#!/usr/bin/env python3
"""
bci_to_source.py - turn Stava's (method signature, bytecode index) into file:line.

WHY THIS IS POSSIBLE AT ALL
  Stava identifies an abstract object by the BCI of the statement that created it
  (BytecodeOffsetTag, read by utils/getBCI.java). javac writes a LineNumberTable mapping
  bytecode offsets to source lines, and javap -l prints it. So the join is exact wherever the
  class was compiled with debug info, which for DaCapo's own jars it was.

WHERE THE CLASS FILES COME FROM
  The Tamiflex Play-Out Agent dumps every loaded class as a loose .class under the benchmark's
  out/ directory (that dump is why -process-dir works at all, since it does not descend into
  jars). So the same tree Stava analysed is the tree javap reads, and there is no version skew
  between the BCIs and the line table.

WHAT IT CANNOT DO
  - No LineNumberTable, no answer. Classes compiled without -g:lines report `no-line-table`
    rather than guessing.
  - A BCI that falls between two table entries is reported at the LAST entry at or before it,
    which is what a debugger does. For a statement spanning several lines that is the line the
    statement STARTS on, not necessarily the one the allocation appears on.
  - ONLY `internal` and `external` objects carry a bytecode offset in the bci field. For a
    `parameter` node that field is the PARAMETER INDEX (-1 being `this`), and for a
    `returnValue` node it is always 0. Feeding either to the line table would silently return
    the line at offset 0 - the method's first line - and look plausible. Those two types are
    resolved to the METHOD DECLARATION line instead, and labelled so.
  - bci -1 is not a real offset. Stava uses it for `this` and for objects with no creating
    statement, so those resolve to `synthetic` and never to a line.
  - Matching is on (method name, erased parameter types). A class with two methods differing
    only in return type - bridge methods from covariant returns - is ambiguous, and both are
    reported with an `ambiguous` marker rather than one being picked silently.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# `public static final synchronized ...` before the return type
MODIFIERS = {"public", "private", "protected", "static", "final", "synchronized",
             "abstract", "native", "transient", "volatile", "strictfp", "default"}

SOOT_SIG = re.compile(r"^<([^:]+):\s*(.+)>$")
LINE_ENTRY = re.compile(r"^\s*line (\d+): (\d+)$")
COMPILED_FROM = re.compile(r'^Compiled from "(.+)"$')


def parse_soot_sig(sig):
    """<pkg.Cls: ret name(a,b)> -> (cls, name, [params]).  None if not a signature."""
    m = SOOT_SIG.match(sig.strip())
    if not m:
        return None
    cls, rest = m.group(1).strip(), m.group(2).strip()
    if "(" not in rest:
        return None
    head, args = rest.split("(", 1)
    args = args.rsplit(")", 1)[0]
    parts = head.split()
    name = parts[-1]
    params = [p.strip() for p in args.split(",") if p.strip()]
    return cls, name, params


def norm_params(params):
    """javap prints erased, fully-qualified types; so does Soot. Normalise whitespace only."""
    return tuple(p.replace(" ", "") for p in params)


def javap_class(classes_dir, fqcn, java_home):
    exe = os.path.join(java_home, "bin", "javap") if java_home else "javap"
    try:
        out = subprocess.run([exe, "-p", "-l", "-classpath", classes_dir, fqcn],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout


def parse_javap(text, fqcn):
    """-> (source_file, {(name, params): [(bci, line), ...] sorted by bci})"""
    src = None
    tables = defaultdict(list)
    cur = None
    in_table = False
    simple = fqcn.rsplit(".", 1)[-1]
    for raw in text.splitlines():
        m = COMPILED_FROM.match(raw.strip())
        if m:
            src = m.group(1)
            continue
        if raw.strip() == "LineNumberTable:":
            in_table = True
            continue
        m = LINE_ENTRY.match(raw)
        if m and in_table:
            if cur is not None:
                tables[cur].append((int(m.group(2)), int(m.group(1))))
            continue
        in_table = False
        s = raw.strip()
        # javap prints the static initialiser as `static {};` - no parameter list at all, so
        # the test below skips it and <clinit> is never registered. That is not a corner case:
        # 17,815 of avrora's objects live in <clinit>, and a static-field store in a static
        # initialiser is the most natural place for STATIC_FIELD_STORE to fire.
        if s == "static {};":
            cur = ("<clinit>", ())
            tables.setdefault(cur, [])
            continue
        # a member declaration ends in ';' and a method one has a parameter list
        if not s.endswith(";") or "(" not in s:
            continue
        s = s[:-1]
        head, args = s.split("(", 1)
        args = args.rsplit(")", 1)[0]
        toks = [t for t in head.split() if t not in MODIFIERS]
        if not toks:
            continue
        name = toks[-1]
        # a constructor prints as `pkg.Cls(...)` with no return type
        if len(toks) == 1 and (name == fqcn or name.endswith("." + simple)
                               or name == simple):
            name = "<init>"
        params = norm_params([p.strip() for p in args.split(",") if p.strip()])
        cur = (name, params)
        tables[cur] = tables.get(cur, [])
    for k in tables:
        tables[k].sort()
    return src, tables


def line_for(table, bci):
    """Last entry at or before bci - the same rule a debugger uses."""
    best = None
    for off, ln in table:
        if off <= bci:
            best = ln
        else:
            break
    return best


class Resolver:
    def __init__(self, classes_dir, java_home):
        self.dir = classes_dir
        self.java_home = java_home
        self.cache = {}
        self.stats = defaultdict(int)

    def load(self, fqcn):
        if fqcn in self.cache:
            return self.cache[fqcn]
        text = javap_class(self.dir, fqcn, self.java_home)
        if text is None:
            self.cache[fqcn] = (None, {})
            self.stats["class-not-found"] += 1
        else:
            self.cache[fqcn] = parse_javap(text, fqcn)
        return self.cache[fqcn]

    def resolve(self, sig, bci, objtype=None):
        p = parse_soot_sig(sig)
        if p is None:
            self.stats["unparsable-signature"] += 1
            return None, "unparsable-signature"
        cls, name, params = p
        src, tables = self.load(cls)
        if src is None:
            return None, "class-not-found"
        key = (name, norm_params(params))
        table = tables.get(key)
        if table is None:
            cands = [k for k in tables if k[0] == name]
            if len(cands) == 1:
                table = tables[cands[0]]
            elif cands:
                self.stats["ambiguous"] += 1
                return None, "ambiguous"
            else:
                self.stats["method-not-found"] += 1
                return None, "method-not-found"
        if not table:
            self.stats["no-line-table"] += 1
            return None, "no-line-table"
        # A parameter's ref is an index and a returnValue's is always 0; neither is an offset.
        # Report the declaration line - the first entry in the table - and say which it is.
        if objtype in ("parameter", "returnValue"):
            decl = table[0][1]
            self.stats["decl-" + objtype] += 1
            if objtype == "parameter":
                which = "this" if str(bci) == "-1" else "arg %s" % bci
                return "%s:%d (decl, %s)" % (src, decl, which), "declaration"
            return "%s:%d (decl, return)" % (src, decl), "declaration"
        try:
            b = int(bci)
        except (TypeError, ValueError):
            self.stats["bad-bci"] += 1
            return None, "bad-bci"
        if b < 0:
            self.stats["synthetic"] += 1
            return None, "synthetic"
        ln = line_for(table, b)
        if ln is None:
            self.stats["bci-before-table"] += 1
            return None, "bci-before-table"
        self.stats["resolved"] += 1
        return "%s:%d" % (src, ln), "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blast", required=True, help="escape-blast.json")
    ap.add_argument("--classes", required=True,
                    help="directory of loose .class files (the Tamiflex dump)")
    ap.add_argument("--java-home", default=os.environ.get("JAVA_HOME", ""))
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", default=None, help="write the annotated json here")
    a = ap.parse_args()

    blast = json.load(open(a.blast, encoding="utf-8"))
    r = Resolver(a.classes, a.java_home)

    rows = []
    for kind, key in (("cause", "appCauses"), ("param", "appParams")):
        for entry in blast.get(key, [])[:a.top]:
            sig, bci, ot = entry.get("method"), entry.get("bci"), entry.get("objType")
            if sig is None:
                # written before escape_blast emitted structured identity
                ps = entry.get("params") or []
                if not (ps and "#" in ps[0]):
                    continue
                sig, bci = ps[0].rsplit("#", 1)
                ot = (entry.get("label") or "").split("@", 1)[0] or None
            where, why = r.resolve(sig, bci, ot)
            rows.append({"kind": kind, "sig": sig, "bci": bci, "objType": ot,
                         "where": where, "why": why,
                         "grossApp": entry.get("grossApp"), "gross": entry.get("gross"),
                         "exclusive": entry.get("exclusive"),
                         "reasons": entry.get("reasons")})

    print("== bci -> source, from %s" % os.path.basename(a.blast))
    print("   classes: %s" % a.classes)
    for kind in ("cause", "param"):
        sel = [x for x in rows if x["kind"] == kind]
        if not sel:
            continue
        print("\n   -- %s" % ("application root causes" if kind == "cause"
                              else "application escaping parameters"))
        print("   %8s %8s  %-40s %s" % ("grossApp", "excl", "source", "reasons"))
        for row in sel:
            print("   %8s %8s  %-40s %s"
                  % (row["grossApp"], row["exclusive"],
                     (row["where"] or "(%s)" % row["why"])[:40],
                     ",".join(row["reasons"] or [])[:36]))
            print("            %s" % row["sig"])

    print("\n   -- resolution outcomes")
    for k in sorted(r.stats, key=lambda x: -r.stats[x]):
        print("   %-22s %6d" % (k, r.stats[k]))

    if a.out:
        blast["sourceMap"] = rows
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(blast, f, indent=1, sort_keys=True)
        print("\n   wrote %s" % a.out)


if __name__ == "__main__":
    main()
