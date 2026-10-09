#!/usr/bin/env python3
"""source_index.py - Stava's (method signature, bci) to the benchmark's own Java source.

bci_to_source.py already maps (method, bci) to File.java:line through the LineNumberTable of the
exact class files Stava analysed (the Tamiflex dump under stava/benchmarks/<b>/out). This adds
the source text: the upstream source release of each benchmark, at the version DaCapo 9.12-MR1
packs, downloaded 2026-09-22 into heapviz/build/sources/ (git-ignored):

  avrora   cmorty/avrora @ 1378b15e05, 2009-12-23: last commit before the jar's cvs-20091224 snapshot
  xalan    xalan-j_2_7_1-src.tar.gz, archive.apache.org
  luindex  lucene-core-2.4.1-sources.jar + lucene-demos-2.4.1-sources.jar, Maven Central
  fop      fop-0.95-src.tar.gz, archive.apache.org (org.apache.fop.fonts.base14 is generated at
           build time and is not in it)
  pmd      pmd-4.2.5-sources.jar, Maven Central
  h2       h2database @ aa85b3545f, 2009-10-11 ("Prepare release"; BUILD_ID 121). Its lines do not
           always match the jar's line table: the jar was built from slightly different text.
  JDK      src.zip of the analysing JDK (Temurin 8u502-b07)

PLACING A LINE. place() takes the line the class file's LineNumberTable gives, then checks it
against what the bytecode at that offset does, read with javap -c: a `new T` must show T (for a
StringBuilder, a `+`, the builder, or `append`), a call must show the method's name, a field read
the field's name. If the line and the three after it do not show it, place() searches outward, at
most RADIUS lines, and reports the shift it needed. A node it cannot place is not shown.
tools/python/source_check.py measures, per benchmark, how many sites sit at shift 0.
"""
import os
import re
import subprocess
import zipfile
from collections import defaultdict

from bci_to_source import MODIFIERS, Resolver, norm_params, parse_soot_sig

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "build", "sources")
STAVA_BENCH = os.path.join(HERE, "..", "..", "stava", "benchmarks")
JAVA_HOME = os.environ.get("JAVA_HOME_STAVA", "/home/harshil/jvm/jdk8u502-b07")
RADIUS = 20

ROOTS = {
    "avrora": ["avrora/avrora-1378b15e05/src"],
    "xalan": ["xalan/xalan-j_2_7_1/src"],
    "luindex": ["luindex"],
    "fop": ["fop/fop-0.95/src/java", "fop/fop-0.95/src/sandbox"],
    "pmd": ["pmd"],
    "h2": ["h2/h2database-aa85b3545f99a8aae5ce022ecc2e5788f9e8bb52/h2/src/main"],
}
CLASS_DIR = {"avrora": "dacapo", "xalan": "xalan", "luindex": "luindex", "fop": "fop",
             "h2": "h2", "pmd": "pmd"}
JDK_PREFIXES = ("java.", "javax.", "sun.", "com.sun.", "jdk.")
INSN = re.compile(r"^\s*(\d+):\s+(\S+)(?:.*//\s*(.*))?$")
BOXES = ("Integer", "Long", "Double", "Float", "Short", "Byte", "Character", "Boolean")


def alloc_pattern(ty):
    """What a line that allocates type ty can look like."""
    simple = ty.split(".")[-1].split("$")[-1].replace("[]", "")
    if ty in ("java.lang.StringBuilder", "java.lang.StringBuffer"):
        return r"\+|StringBu(ilder|ffer)|append"
    if ty.endswith("[]"):
        return r"new\s+[\w.$]+\s*\[|\{|\.\.\.|toArray|clone\("
    if ty.startswith("java.lang.") and simple in BOXES:
        return r"new\s+%s\b|\w" % simple          # autoboxing leaves no trace in the text
    if simple.isdigit():
        return r"new\s+[\w.$<>]+\s*\("            # anonymous class Outer$N: `new Iface() {`
    return r"new\s+[\w.$<>]*%s\b" % re.escape(simple)


class Sources:
    def __init__(self, bench):
        self.bench = bench
        self.classes = os.path.join(STAVA_BENCH, CLASS_DIR[bench], "out")
        self.resolver = Resolver(self.classes, JAVA_HOME)
        self.roots = [os.path.join(SRC, r) for r in ROOTS[bench]]
        self._jdk = None
        self._lines = {}
        self._code = {}

    # ---- files -------------------------------------------------------------------------
    def jdk(self):
        if self._jdk is None:
            self._jdk = zipfile.ZipFile(os.path.join(JAVA_HOME, "src.zip"))
        return self._jdk

    def path_of(self, cls, file_name):
        """(kind, path) of the source file declaring class cls, compiled from file_name."""
        pkg = cls.rsplit(".", 1)[0].replace(".", "/") if "." in cls else ""
        rel = (pkg + "/" if pkg else "") + file_name
        if cls.startswith(JDK_PREFIXES):
            try:
                self.jdk().getinfo(rel)
                return "jdk", rel
            except KeyError:
                return None, rel
        for r in self.roots:
            p = os.path.join(r, rel)
            if os.path.exists(p):
                return "file", p
        return None, rel

    def lines_of(self, kind, path):
        key = (kind, path)
        if key not in self._lines:
            if kind == "jdk":
                text = self.jdk().read(path).decode("utf-8", "replace")
            else:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            self._lines[key] = text.splitlines()
        return self._lines[key]

    # ---- bytecode ----------------------------------------------------------------------
    def code(self, cls):
        """{(method name, params): {bci: (opcode, constant-pool comment)}} from javap -c."""
        if cls in self._code:
            return self._code[cls]
        out = defaultdict(dict)
        cp = "" if cls.startswith(JDK_PREFIXES) else self.classes
        exe = os.path.join(JAVA_HOME, "bin", "javap")
        try:
            r = subprocess.run([exe, "-p", "-c"] + (["-classpath", cp] if cp else []) + [cls],
                               capture_output=True, text=True, timeout=180)
            text = r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            text = ""
        simple, cur = cls.rsplit(".", 1)[-1], None
        for raw in text.splitlines():
            m = INSN.match(raw)
            if m and cur is not None:
                out[cur][int(m.group(1))] = (m.group(2), (m.group(3) or "").strip())
                continue
            s = raw.strip()
            if s == "static {};":
                cur = ("<clinit>", ())
                continue
            if not s.endswith(";") or "(" not in s or s.startswith("//"):
                continue
            head, args = s[:-1].split("(", 1)
            toks = [t for t in head.split() if t not in MODIFIERS]
            if not toks:
                continue
            name = toks[-1]
            if len(toks) == 1 and (name == cls or name.endswith("." + simple) or name == simple):
                name = "<init>"
            cur = (name, norm_params([p.strip() for p in args.rsplit(")", 1)[0].split(",")
                                      if p.strip()]))
        self._code[cls] = dict(out)
        return self._code[cls]

    def insn(self, sig, bci):
        q = parse_soot_sig(sig)
        methods = self.code(q[0])
        m = methods.get((q[1], norm_params(q[2])))
        if m is None:
            cands = [v for k, v in methods.items() if k[0] == q[1]]
            m = cands[0] if len(cands) == 1 else {}
        return m.get(int(bci))

    def pattern(self, sig, bci, objtype, alloc_type=None):
        """Regex a correctly placed line must match, or None when nothing distinctive is known."""
        q = parse_soot_sig(sig)
        if objtype in ("parameter", "returnValue"):
            name = q[0].rsplit(".", 1)[-1].split("$")[-1] if q[1] == "<init>" else q[1]
            return r"\b%s\s*\(" % re.escape(name)
        if alloc_type:
            return alloc_pattern(alloc_type)
        ins = self.insn(sig, bci)
        if not ins:
            return None
        op, comment = ins
        if op.startswith("invoke"):
            m = re.search(r"Method\s+(?:[\w/$]+\.)?(?:\"<init>\"|([\w$]+)):", comment)
            if m and m.group(1):
                return r"\b%s\s*\(" % re.escape(m.group(1))
            return None
        if op in ("getfield", "getstatic"):
            m = re.search(r"Field\s+(?:[\w/$]+\.)?([\w$]+):", comment)
            return r"\b%s\b" % re.escape(m.group(1)) if m else None
        if op == "aaload":
            return r"\["
        if op in ("new", "anewarray", "newarray", "multianewarray"):
            m = re.search(r"class\s+([\w/$\[\];]+)", comment)
            t = m.group(1).replace("/", ".") if m else ""
            return alloc_pattern(t) if t else r"new\s"
        return None

    # ---- lines -------------------------------------------------------------------------
    def locate(self, sig, bci, objtype="internal"):
        """The line the class file's LineNumberTable gives: dict(file, line, kind, path, rel)."""
        loc, why = self.resolver.resolve(sig, bci, objtype)
        if loc is None:
            return {"error": why}
        fname, _, rest = loc.partition(":")
        line = int(rest.split()[0])
        q = parse_soot_sig(sig)
        kind, path = self.path_of(q[0], fname)
        if kind is None:
            return {"error": "no source file for %s (%s)" % (q[0], path), "file": fname,
                    "line": line}
        rel = path if kind == "jdk" else os.path.relpath(path, SRC).replace(os.sep, "/")
        return {"file": fname, "line": line, "class_line": line, "shift": 0, "kind": kind,
                "path": path, "rel": rel}

    def place(self, sig, bci, objtype="internal", alloc_type=None):
        """locate(), then checked against the bytecode and moved if needed (see the module
        docstring). Adds 'shift' and 'checked' (False when no pattern was available)."""
        loc = self.locate(sig, bci, objtype)
        if "error" in loc:
            return loc
        rx = self.pattern(sig, bci, objtype, alloc_type)
        if rx is None:
            loc["checked"] = False
            return loc
        lines = self.lines_of(loc["kind"], loc["path"])
        pat = re.compile(rx)
        n = loc["line"]
        # a declaration must be on its own line; a `new` inside a long statement can sit several
        # lines below the line the statement starts on, which is the one the table records
        span = 0 if objtype in ("parameter", "returnValue") else (8 if alloc_type else 3)

        def hit(ln):
            return 1 <= ln <= len(lines) and bool(pat.search(" ".join(lines[ln - 1:ln + span])))
        for d in sorted(range(-RADIUS, RADIUS + 1), key=lambda d: (abs(d), d)):
            if hit(n + d):
                # highlight the line that shows it, inside the statement the table points at;
                # `shift` keeps how far that statement is from the table's line (0 = agrees)
                at = next((ln for ln in range(n + d, n + d + span + 1)
                           if 1 <= ln <= len(lines) and pat.search(lines[ln - 1])), n + d)
                loc.update(line=at, shift=d, checked=True)
                return loc
        return {"error": "line does not show it within %d lines" % RADIUS, "file": loc["file"],
                "line": n}

    def snippet(self, loc, before=2, after=2):
        """[(lineno, text, is_target)] around loc['line']."""
        lines = self.lines_of(loc["kind"], loc["path"])
        n = loc["line"]
        lo, hi = max(1, n - before), min(len(lines), n + after)
        return [(i, lines[i - 1], i == n) for i in range(lo, hi + 1)]
