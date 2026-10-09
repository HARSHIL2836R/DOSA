#!/usr/bin/env python3
"""
reason_source_map.py - for every EscapeReason: the ALLOCATION site and the ESCAPE site.

WHAT THIS IS, AND HOW IT DIFFERS FROM bci_to_source.py
  bci_to_source maps the top-N blast CAUSES to file:line - a ranked shortlist, not a mapping.
  This walks every application object in <dirname>.reasons and reports, per reason, where the
  object was created and where it escaped.

THE TWO SITES ARE NOT THE SAME THING, AND ONLY ONE OF THEM IS RECORDED
  ALLOCATION SITE - recorded, exact.
      The object's own (method, bci). For `internal` that is the `new`. For `external` it is
      the call or field-load that produced the handle, which is an origin rather than an
      allocation and is labelled `origin`. For `parameter` the bci is the ARGUMENT INDEX and
      for `returnValue` it is always 0, so both resolve to the method declaration line.

  ESCAPE SITE - NOT recorded. Derived here, and sometimes ambiguous.
      EscapeReasons.record(SootMethod, ObjectNode, EscapeReason) takes no Unit and no bci, so
      Stava never stores where a reason fired. What it does store is the enclosing method. For
      the five reasons whose construct is a single visible opcode, this finds every occurrence
      of that opcode in the enclosing method and reports the lines:

          MONITOR             monitorenter
          THROWN              athrow
          STATIC_FIELD_STORE  putstatic
          STATIC_FIELD_LOAD   getstatic
          CONSTANT_OBJECT     ldc / ldc_w / ldc2_w

      `exact` in the output means the method contained exactly ONE such opcode, so the escape
      site is unambiguous. More than one and every candidate is listed. Zero and the reason was
      never earned in that method at all - see below. Reasons with no single opcode
      (TRANSITIVE_SUCCESSOR, ASSIGNED_TO_THIS_OR_PARAM, RETURNED, ...) report `n/a`; getting a
      real escape site for those needs an instrumentation change, not a smarter lookup.

THE ZERO-CANDIDATE CASE IS THE INTERESTING ONE
  Component-wide attribution (Reason-Pipeline-Spec X-A4) stamps a reason that fired on ONE
  member of a resolver component onto ALL of them, so a method can carry MONITOR with no
  monitorenter anywhere in it: avrora.actions.CFGAction has zero monitorenter instructions and
  three of its methods report MONITOR. Those objects are counted as `unwitnessed`, which
  measures the stamping error directly, per reason, rather than inferring it from a
  4-reasons/50-members threshold.

RESTRICTING TO UNIVERSAL PATTERNS
  --only-sets takes the json from common_reason_sets.py and keeps only objects whose EXACT
  reason set occurs in every benchmark. A pattern that survives six unrelated programs is a
  property of how Java is written rather than of one benchmark, which is the set worth
  pointing at source.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bci_to_source import MODIFIERS, Resolver, parse_soot_sig, line_for  # noqa: E402
from info_to_graph import find_reasons_file, read_reasons  # noqa: E402

WITNESS = {
    "MONITOR": ("monitorenter",),
    "THROWN": ("athrow",),
    "STATIC_FIELD_STORE": ("putstatic",),
    "STATIC_FIELD_LOAD": ("getstatic",),
    "CONSTANT_OBJECT": ("ldc", "ldc_w", "ldc2_w"),
}

OPCODE = re.compile(r"^\s*(\d+):\s+(\S+)")


class Bytecode:
    """Per-class {method name: {opcode: [bytecode offsets]}}. One javap per class, cached."""

    def __init__(self, classes_dir, java_home):
        self.dir = classes_dir
        self.java_home = java_home
        self.cache = {}
        self.missing = set()

    def offsets(self, fqcn, mname, opcodes):
        if fqcn not in self.cache:
            self.cache[fqcn] = self._load(fqcn)
        m = self.cache[fqcn].get(mname)
        if m is None:
            return None
        out = []
        for op in opcodes:
            out.extend(m.get(op, ()))
        return sorted(out)

    def _load(self, fqcn):
        exe = os.path.join(self.java_home, "bin", "javap") if self.java_home else "javap"
        try:
            r = subprocess.run([exe, "-p", "-c", "-classpath", self.dir, fqcn],
                               capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            self.missing.add(fqcn)
            return {}
        if r.returncode != 0 or not r.stdout.strip():
            self.missing.add(fqcn)
            return {}
        out, cur = {}, None
        simple = fqcn.rsplit(".", 1)[-1]
        for raw in r.stdout.splitlines():
            s = raw.strip()
            # An instruction line is never a method header. Checked FIRST because an instruction's
            # constant-pool comment can end in ";" and contain "(" - e.g.
            #   274: invokevirtual #102  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
            # - and the header test below used to take it for a new method, filing every later
            # opcode under a bogus name. Found 2026-09-14 by tools/python/own_witness.py: athrow at
            # CommandLineOptions.createRenderer bci 307 was reported absent.
            m = OPCODE.match(raw)
            if m:
                if cur is not None:
                    out[cur].setdefault(m.group(2), []).append(int(m.group(1)))
                continue
            # `static {};` is the static initialiser and has no parameter list; see the same
            # note in bci_to_source.parse_javap.
            if s == "static {};":
                cur = "<clinit>"
                out.setdefault(cur, {})
                continue
            if s.endswith(";") and "(" in s and not s.startswith("//"):
                # modifiers stripped first: `private pkg.Cls(...)` is a constructor, and
                # without this only package-private constructors were recognised as <init>
                # (found 2026-09-14 on xalan CharInfo, whose athrows sit in private ones)
                toks = [t for t in s[:-1].split("(", 1)[0].split() if t not in MODIFIERS]
                name = toks[-1] if toks else ""
                if len(toks) == 1 and (name == fqcn or name.endswith("." + simple)):
                    name = "<init>"
                cur = name
                out.setdefault(cur, {})
                continue
            m = OPCODE.match(raw)
            if m and cur is not None:
                out[cur].setdefault(m.group(2), []).append(int(m.group(1)))
        return out


def line_table_for(res, cls, mname):
    """The LineNumberTable of any method with this name, via the Resolver's cache."""
    src, tables = res.load(cls)
    if src is None:
        return None, None
    for (name, _params), tbl in tables.items():
        if name == mname and tbl:
            return src, tbl
    return src, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--classes", required=True, help="loose .class tree (Tamiflex dump)")
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--java-home", default=os.environ.get("JAVA_HOME", ""))
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-sets", default=None,
                    help="json from common_reason_sets.py: keep only objects whose EXACT "
                         "reason set is universal across the benchmarks")
    ap.add_argument("--top-sites", type=int, default=8)
    a = ap.parse_args()

    keep = None
    if a.only_sets:
        cs = json.load(open(a.only_sets, encoding="utf-8"))
        keep = {tuple(e["set"]) for e in cs["commonSets"]}
        print("   restricting to %d universal reason sets" % len(keep))

    rp = find_reasons_file(a.info_dir, None)
    if rp is None:
        raise SystemExit("no .reasons in %s" % a.info_dir)
    # raw: a root cause inherited from a successor fired in ANOTHER method, so looking for
    # its opcode here would count it as unwitnessed
    reasons = read_reasons(rp, mode="raw")

    res = Resolver(a.classes, a.java_home)
    bc = Bytecode(a.classes, a.java_home)

    # reason -> (allocSite, escapeSite, kind, cls, mname, bci) -> objects.
    # cls/mname/bci are carried so a renderer can pull the disassembly for the exact method
    # rather than re-parsing a display string.
    pairs = defaultdict(Counter)
    per_reason = Counter()
    witnessed, unwitnessed, ambiguous, na = Counter(), Counter(), Counter(), Counter()
    objects = 0

    for (sig, bci, objtype), names in reasons.items():
        if not names:
            continue
        if keep is not None and tuple(names) not in keep:
            continue
        p = parse_soot_sig(sig)
        if p is None:
            continue
        cls, mname, _ = p
        if not any(cls.startswith(x) for x in a.class_prefix):
            continue
        objects += 1

        alloc, why = res.resolve(sig, bci, objtype)
        alloc = alloc or "(%s)" % why
        akind = {"internal": "alloc", "external": "origin"}.get(objtype, "decl")

        for r in names:
            per_reason[r] += 1
            if r not in WITNESS:
                na[r] += 1
                pairs[r][(alloc, "n/a - no single opcode", akind, cls, mname, bci)] += 1
                continue
            offs = bc.offsets(cls, mname, WITNESS[r])
            if not offs:
                unwitnessed[r] += 1
                pairs[r][(alloc, "NONE IN METHOD - inherited (X-A4)", akind, cls, mname, bci)] += 1
                continue
            witnessed[r] += 1
            src, tbl = line_table_for(res, cls, mname)
            if tbl:
                lines = sorted({line_for(tbl, o) for o in offs} - {None})
                esc = "%s:%s" % (src, ",".join(str(x) for x in lines))
            else:
                esc = "%s:? (bci %s)" % (src or cls, ",".join(str(o) for o in offs))
            if len(offs) > 1:
                ambiguous[r] += 1
                esc += "  [%d candidates]" % len(offs)
            pairs[r][(alloc, esc, akind, cls, mname, bci)] += 1

    print("== %s   reason -> (allocation site, escape site)" % a.label)
    print("   .reasons : %s" % os.path.basename(rp))
    print("   application objects mapped : %d" % objects)
    print("   classes javap could not read: %d" % len(bc.missing))
    print("\n   %-26s %8s %10s %11s %10s %7s"
          % ("reason", "objects", "witnessed", "unwitnessed", "ambiguous", "n/a"))
    for r in sorted(per_reason, key=lambda k: -per_reason[k]):
        print("   %-26s %8d %10s %11s %10s %7s"
              % (r, per_reason[r],
                 witnessed[r] if r in WITNESS else "-",
                 unwitnessed[r] if r in WITNESS else "-",
                 ambiguous[r] if r in WITNESS else "-",
                 na[r] if r not in WITNESS else "-"))

    print("\n   -- sites per reason (top %d by object count)" % a.top_sites)
    for r in sorted(per_reason, key=lambda k: -per_reason[k]):
        print("\n   %s  (%d objects, %d distinct site pairs)"
              % (r, per_reason[r], len(pairs[r])))
        for (al, es, kind, _c2, _m2, _b2), c in pairs[r].most_common(a.top_sites):
            print("      %6d  %-5s %-38s  ->  %s" % (c, kind, al[:38], es))

    out = {
        "meta": {"label": a.label, "reasons": os.path.basename(rp),
                 "appPrefixes": a.class_prefix, "objects": objects,
                 "onlySets": a.only_sets,
                 "allocSite": "recorded exactly: the object's own (method, bci). "
                              "kind=alloc for internal, origin for external (a call or field "
                              "load, not an allocation), decl for parameter/returnValue.",
                 "escapeSite": "NOT recorded by Stava - record() takes no Unit. Derived by "
                               "finding the witnessing opcode in the enclosing method. "
                               "'[n candidates]' means the method has n of them and the true "
                               "one is unknown. 'NONE IN METHOD' means the reason was "
                               "inherited from a resolver component (X-A4)."},
        "reasons": [
            {"reason": r, "objects": per_reason[r],
             "witnessed": witnessed[r] if r in WITNESS else None,
             "unwitnessed": unwitnessed[r] if r in WITNESS else None,
             "ambiguous": ambiguous[r] if r in WITNESS else None,
             "sites": [{"allocSite": al, "allocKind": kind, "escapeSite": es, "objects": c,
                        "cls": kls, "mname": mn,
                        "bciInt": (int(bb) if str(bb).lstrip("-").isdigit() else None)}
                       for (al, es, kind, kls, mn, bb), c in pairs[r].most_common()]}
            for r in sorted(per_reason, key=lambda k: -per_reason[k])],
        "resolutionOutcomes": dict(res.stats),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print("\n   wrote %s" % a.out)


if __name__ == "__main__":
    main()
