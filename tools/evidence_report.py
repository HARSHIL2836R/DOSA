#!/usr/bin/env python3
"""evidence_report.py - benchmark source code for each claim in the 2026-09-22 update to the
advisor, a few examples per benchmark, as one HTML page.

    python3 tools/evidence_report.py --out render/figures/evidence-p6.html

Claims, as sent:
  A  TRANSITIVE_SUCCESSOR / PARAM_ESCAPES_VIA_SUCCESSOR repeat a reason the object already has.
     Examples: allocation sites whose raw reasons hold a propagated reason AND a direct one, and
     whose propagated reason resolves (roots mode) to nothing beyond the direct ones.
  B  Stava counts one allocation several times: a node in every method that gets the object as a
     call result or field read. Examples: sites with aliases, in other methods, that Spark maps to
     that site alone.
  C  The resolver escapes a whole component at once, so one member's reason shows on all. Examples:
     sites carrying an inherited reason, next to the component member where it fired (members share
     the component's pointer group, .reasons column 5).
  D  Single-reason share by run (numbers only).
  E  Escape through a parameter; the most shared parameter. Examples: sites of each benchmark's
     largest hub, and for the StringBuilder hub the JDK code that makes its receiver escape.

Inputs: /tmp/rv/p6info/<bench>-false (patch-0006 runs), build/out/{param-hubs,alloc-unit}/*.json,
build/sources/ (extract/source_index.py). Every snippet is located through the LineNumberTable of
the analysed class, and tools/source_check.py measures how often that lands on a matching line.
"""
import argparse
import glob
import html
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from alloc_sites import read_alloc  # noqa: E402
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import REASONS_PROPAGATED, read_reasons, read_via  # noqa: E402
from source_index import Sources  # noqa: E402

OUT_DIR = os.path.join(HERE, "..", "build", "out")
BENCH = [("avrora", ["avrora."]), ("xalan", ["org.apache.xalan.", "org.apache.xpath.",
                                            "org.apache.xml."]),
         ("luindex", ["org.apache.lucene."]), ("fop", ["org.apache.fop."]), ("h2", ["org.h2."]),
         ("pmd", ["net.sourceforge.pmd."])]
LICENSE = {"avrora": "UCLA licence (avrora, Ben L. Titzer)", "xalan": "Apache License 2.0",
           "luindex": "Apache License 2.0 (Lucene)", "fop": "Apache License 2.0",
           "h2": "EPL 1.0 / MPL 1.1 (H2)", "pmd": "BSD-style (PMD)"}
PROP = set(REASONS_PROPAGATED)
PER = 2          # examples per benchmark per claim


def esc(s):
    return html.escape(str(s))


class Bench:
    def __init__(self, name, prefixes):
        self.name, self.prefixes = name, prefixes
        self.dir = "/tmp/rv/p6info/%s-false" % name
        rp = glob.glob(self.dir + "/*.reasons")[0]
        self.raw = read_reasons(rp, mode="raw")
        self.roots = read_reasons(rp, mode="roots")
        self.via = read_via(rp[:-len(".reasons")] + ".via")
        self.cols = {}
        with open(rp, encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                self.cols[(p[0], int(p[1]), p[2])] = p
        self.alloc = read_alloc(glob.glob(self.dir + "/*.alloc")[0])[0]
        self.src = Sources(name)

    def is_app(self, sig):
        q = parse_soot_sig(sig)
        return q is not None and any(q[0].startswith(x) for x in self.prefixes)

    def sites(self):
        return sorted(k for k, v in self.alloc.items()
                      if v[0] == "NEW" and k[2] == "internal" and self.is_app(k[0]))

    def own(self, k):
        return set(self.raw.own.get(k, ())) if self.raw.own is not None else set()

    def group(self, k, col):
        p = self.cols.get(k)
        return p[col] if p and len(p) > col and p[col] else None


def type_of(b, k):
    kind, sset = b.alloc.get(k, ("", []))
    if kind == "NEW":
        return next((s[2] for s in sset if isinstance(s, tuple)), None)
    return None


def code_block(b, k, label, before=2, after=2):
    """HTML for the source around node k = (method, bci, type), or None when the line cannot be
    confirmed against the bytecode (source_index.Sources.place)."""
    loc = b.src.place(k[0], k[1], k[2], type_of(b, k) if k[2] == "internal" else None)
    if "error" in loc or not loc.get("checked"):
        return None
    rows = b.src.snippet(loc, before, after)
    body = "".join('<tr class="%s"><td class="n">%d</td><td><code>%s</code></td></tr>'
                   % ("hit" if hit else "", n, esc(t.rstrip()) or "&nbsp;") for n, t, hit in rows)
    where = "%s:%d" % (loc["rel"], loc["line"])
    if k[2] in ("parameter", "returnValue"):
        # the class file records no declaration line (bci_to_source reports the first code line),
        # so moving to the declaration says nothing about the release text
        note = " (method declaration)"
    elif loc["shift"]:
        note = (" (the class file says line %d; this release's text is %+d lines off here, "
                "matched by what the bytecode does)" % (loc["class_line"], loc["shift"]))
    else:
        note = ""
    return ('<div class="code"><div class="cap"><b>%s</b> <span>%s%s</span></div>'
            '<table>%s</table></div>' % (esc(label), esc(where), esc(note), body))


def short(sig):
    q = parse_soot_sig(sig)
    return "%s.%s" % (q[0].split(".")[-1], q[1]) if q else sig


def what(b, k):
    """What node k is, in words: for an external, what the bytecode at its offset does."""
    if k[2] == "internal":
        return "the allocation at bci %d" % k[1]
    if k[2] == "parameter":
        return "parameter %s" % ("this" if k[1] == -1 else k[1])
    if k[2] == "returnValue":
        return "the return value"
    ins = b.src.insn(k[0], k[1])
    if ins:
        op, comment = ins
        if op.startswith("invoke"):
            m = re.search(r"Method\s+(?:([\w/$]+)\.)?([\w$\"<>]+):", comment)
            if m:
                owner = m.group(1).split("/")[-1] if m.group(1) else short(k[0]).split(".")[0]
                return "the result of calling %s.%s()" % (owner, m.group(2))
        if op in ("getfield", "getstatic"):
            m = re.search(r"Field\s+(?:([\w/$]+)\.)?([\w$]+):", comment)
            if m:
                return "the value of %sfield %s" % ("static " if op == "getstatic" else "",
                                                     m.group(2))
        if op == "aaload":
            return "an array element read"
    return "a call result or field read at bci %d" % k[1]


def node_name(b, k):
    return "%s in %s" % (what(b, k), short(k[0]))


def claim_a(b):
    cands = []
    for k in b.sites():
        raw = set(b.raw.get(k, ()))
        prop, direct = raw & PROP, raw - PROP
        if not prop or not direct or set(b.roots.get(k, ())) != direct:
            continue
        g = b.group(k, 6) or b.group(k, 4)
        targets = [t for t in b.via.get(int(g), ()) if t in b.cols] if g else []
        # prefer a successor in another method: the repeat is then visible across frames
        targets.sort(key=lambda t: (t[0] == k[0], t[2] == "returnValue", t))
        if targets:
            cands.append((targets[0][0] == k[0], k, targets[0], prop, direct))
    out = []
    for _same, k, t, prop, direct in sorted(cands, key=lambda c: (c[0], c[1])):
        a1 = code_block(b, k, "the object")
        a2 = code_block(b, t, "the successor its %s points at" % "/".join(sorted(prop)))
        if not a1 or not a2:
            continue
        out.append(
            "<p>%s escapes for <code>%s</code>. Stava also records <code>%s</code>, pointing at %s, "
            "whose own reasons are <code>%s</code>. Followed to their causes, the propagated "
            "reasons add nothing: roots mode gives <code>%s</code>.</p>%s%s"
            % (esc(node_name(b, k)), esc(", ".join(sorted(direct))), esc(", ".join(sorted(prop))),
               esc(node_name(b, t)), esc(", ".join(b.raw.get(t, ())) or "none"),
               esc(", ".join(b.roots.get(k, ()))), a1, a2))
        if len(out) >= PER:
            break
    return out


def claim_b(b):
    """Sites whose aliases each have a Spark set of exactly this one site: nothing else, library
    or Spark-made, could be what those nodes hold."""
    aliases = defaultdict(list)
    for k, (kind, sset) in b.alloc.items():
        if kind != "PTS" or k[2] != "external" or not b.is_app(k[0]):
            continue
        if len(sset) == 1 and isinstance(sset[0], tuple) and b.is_app(sset[0][0]):
            aliases[(sset[0][0], sset[0][1])].append(k)
    out = []
    for site in sorted(aliases, key=lambda s: (-len({a[0] for a in aliases[s]}), s)):
        k = (site[0], site[1], "internal")
        if b.alloc.get(k, ("",))[0] != "NEW":
            continue
        # one alias per other method; field reads and calls into the application first
        per_method = {}
        for a in sorted(aliases[site]):
            if a[0] != site[0]:
                per_method.setdefault(a[0], a)

        def rank(a):
            ins = b.src.insn(a[0], a[1]) or ("", "")
            same_class = re.search(r"Method\s+[\w$]+:", ins[1]) is not None
            app_call = ins[0].startswith("invoke") and (same_class or any(
                ("Method " + p.replace(".", "/")) in ins[1] for p in b.prefixes))
            return (0 if ins[0] in ("getfield", "getstatic") else 1 if app_call else 2, a)
        others = sorted(per_method.values(), key=rank)
        if len(others) < 2 or rank(others[1])[0] == 2:
            continue
        blocks = [code_block(b, k, "the allocation (1 node)")]
        for a in others[:3]:
            blocks.append(code_block(b, a, "another node for the same object: %s"
                                     % node_name(b, a)))
        if any(x is None for x in blocks):
            continue
        out.append("<p>One allocation site, %s, is %d Stava nodes: the allocation, and %d nodes in "
                   "%d other methods whose Spark points-to set is this site and nothing else. "
                   "Three of them:</p>%s"
                   % (esc(node_name(b, k)), 1 + len(aliases[site]), len(aliases[site]),
                      len(per_method), "".join(blocks)))
        if len(out) >= PER:
            break
    return out


def claim_c(b):
    members = defaultdict(list)
    for k, p in b.cols.items():
        if len(p) > 4 and p[4]:
            members[p[4]].append(k)
    cands = []
    for k in b.sites():
        inh = set(b.raw.get(k, ())) - b.own(k)
        g = b.group(k, 4)
        if not inh or not g:
            continue
        fired = [m for m in members[g] if m != k and b.own(m) & inh]
        # where it fired: application code with a code line first, then a parameter, then JDK
        fired.sort(key=lambda m: (not b.is_app(m[0]), m[2] not in ("internal", "external"), m))
        if fired:
            m = fired[0]
            cands.append(((not b.is_app(m[0]), len(members[g]) > 1000), k, m, g, inh))
    out, used = [], set()
    for _key, k, m, g, inh in sorted(cands, key=lambda c: (c[0], c[1])):
        if g in used:
            continue
        c1 = code_block(b, k, "the object carrying the inherited reason")
        c2 = code_block(b, m, "a member of its component where the reason fired")
        if not c1 or not c2:
            continue
        r = sorted(b.own(m) & inh)
        used.add(g)
        out.append("<p>%s carries <code>%s</code> without it firing there (own reasons: <code>%s</code>). "
                   "It fired on %s, in the same resolver component; the resolver escapes the "
                   "component as a whole (%s members).</p>%s%s"
                   % (esc(node_name(b, k)), esc(", ".join(r)),
                      esc(", ".join(sorted(b.own(k))) or "none"), esc(node_name(b, m)),
                      format(len(members[g]), ","), c1, c2))
        if len(out) >= PER:
            break
    return out


def claim_e(b, hubs_json, objects_json):
    out = []
    top = hubs_json["top"][0] if hubs_json.get("top") else None
    sb = [t for t in hubs_json.get("top", []) if "StringBu" in t["method"] and t["param"] == -1]
    hub = sb[0] if sb else top
    if hub is None:
        return out, None
    key = "hub %s <%d>" % (hub["method"], hub["param"])
    sites = objects_json.get(key, [])
    shown = 0
    for m, bci in sites:
        blk = code_block(b, (m, bci, "internal"), "a site routed through this parameter", 1, 2)
        if blk is None:
            continue
        out.append(blk)
        shown += 1
        if shown >= 3:
            break
    return out, hub


def members_of(b):
    """{column-5 group: [nodes]}: the members of one resolver component share that group."""
    if not hasattr(b, "_members"):
        m = defaultdict(list)
        for k, p in b.cols.items():
            if len(p) > 4 and p[4]:
                m[p[4]].append(k)
        b._members = m
    return b._members


def component_cause(b, start):
    """A member of start's resolver component where one of start's inherited reasons fired,
    application code first. -> (member, reasons) or None."""
    inh = set(b.raw.get(start, ())) - b.own(start) - PROP
    g = b.group(start, 4)
    if not inh or not g:
        return None
    fired = [m for m in members_of(b)[g] if m != start and b.own(m) & inh]
    fired.sort(key=lambda m: (not b.is_app(m[0]), m[2] not in ("internal", "external"), m))
    return (fired[0], sorted(b.own(fired[0]) & inh)) if fired else None


def cause_chain(b, start, depth=4):
    """Follow own successor pointers (.reasons column 7) from `start` to the nearest node whose
    own reasons include a direct cause other than RETURNED (a returned value escapes only if the
    caller's copy does). -> [start, ..., cause] or None."""
    frontier, parent, seen = [start], {start: None}, {start}
    for _ in range(depth):
        nxt = []
        for x in frontier:
            g = b.group(x, 6)
            for t in sorted(b.via.get(int(g), ())) if g else ():
                if t in seen or t not in b.cols:
                    continue
                seen.add(t)
                parent[t] = x
                if b.own(t) - PROP - {"RETURNED"}:
                    chain = [t]
                    while parent[chain[-1]] is not None:
                        chain.append(parent[chain[-1]])
                    return chain[::-1]
                nxt.append(t)
        frontier = nxt
    return None


def page(sections, summary):
    css = """
:root{--bg:#fbfbfa;--fg:#1d1d1f;--mut:#5f6368;--line:#e3e3e0;--code:#f3f3f1;--hit:#fff2b3;--acc:#1f5fbf}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17181a;--fg:#e8e8e6;--mut:#a0a3a8;--line:#2e3034;--code:#202225;--hit:#4a4220;--acc:#8ab4f8}}
:root[data-theme="dark"]{--bg:#17181a;--fg:#e8e8e6;--mut:#a0a3a8;--line:#2e3034;--code:#202225;--hit:#4a4220;--acc:#8ab4f8}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 6px}h2{font-size:20px;margin:40px 0 8px;border-top:1px solid var(--line);padding-top:20px}
h3{font-size:16px;margin:22px 0 6px;color:var(--acc)}p{margin:8px 0}.mut{color:var(--mut);font-size:13px}
code{font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
.code{border:1px solid var(--line);border-radius:6px;margin:8px 0 14px;overflow:hidden}
.cap{background:var(--code);padding:6px 10px;font-size:13px;border-bottom:1px solid var(--line)}.cap span{color:var(--mut);overflow-wrap:anywhere}.cap{overflow-wrap:anywhere}
.code table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}
.code td{padding:1px 10px;white-space:pre;vertical-align:top}.code td.n{color:var(--mut);text-align:right;user-select:none;width:1%}
tr.hit td{background:var(--hit)}
p code{overflow-wrap:anywhere}.scroll{overflow-x:auto}
table.sum{border-collapse:collapse;margin:8px 0;font-size:14px}table.sum td,table.sum th{border:1px solid var(--line);padding:4px 10px;text-align:right}
table.sum th:first-child,table.sum td:first-child{text-align:left}
"""
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Escape Claims Evidence</title><style>%s</style></head><body><main>%s%s</main></body></html>"
            % (css, summary, "".join(sections)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    benches = [Bench(n, p) for n, p in BENCH]
    secA, secB, secC, secE = [], [], [], []
    rows = []
    for b in benches:
        au = json.load(open(os.path.join(OUT_DIR, "alloc-unit", b.name + "-false.json")))
        ph = json.load(open(os.path.join(OUT_DIR, "param-hubs", b.name + "-false-p6.json")))
        oj = json.load(open(os.path.join(OUT_DIR, "param-hubs", b.name + "-false.objects.json")))
        rules = au["rules"]["own node only"]
        rows.append((b.name, au["nodes"], au["sites"], rules["single"],
                     100.0 * ph["routedSites"] / ph["escaping"] if ph["escaping"] else 0))
        lic = '<p class="mut">Source: %s.</p>' % esc(LICENSE[b.name])
        ex = claim_a(b)
        secA.append("<h3>%s</h3>%s%s" % (b.name, lic, "".join(ex) or "<p class=mut>No example found.</p>"))
        ex = claim_b(b)
        secB.append("<h3>%s</h3>%s%s" % (b.name, lic, "".join(ex) or "<p class=mut>No example found.</p>"))
        ex = claim_c(b)
        secC.append("<h3>%s</h3>%s%s" % (b.name, lic, "".join(ex) or "<p class=mut>No example found.</p>"))
        blocks, hub = claim_e(b, ph, oj)
        which = ("receiver" if hub and hub["param"] == -1 else
                 "argument %d" % hub["param"] if hub else "")
        head = ("<p>Largest parameter hub%s: <code>%s</code>, its %s, routing %d allocation sites. "
                "That parameter's reasons (roots mode): <code>%s</code>.</p>"
                % (" of StringBuilder/StringBuffer" if "StringBu" in hub["method"] else "",
                   esc(hub["method"]), which, hub["sites"], esc(", ".join(hub["reasons"])))
                if hub else "")
        extra = ""
        start = (hub["method"], hub["param"], "parameter") if hub else None
        chain = cause_chain(b, start) if hub else None
        comp = component_cause(b, start) if hub and not chain else None
        if comp:
            m, rs = comp
            blk = code_block(b, m, "the component member where it fired", 4, 3)
            extra = ("<p>Why Stava marks the parameter escaping: its own pointers end only in "
                     "<code>RETURNED</code>. The <code>%s</code> it carries is inherited from its "
                     "resolver component (%s members), where it fired on %s. Stava decides a "
                     "parameter once for every caller, so one caller's escape is every caller's.</p>%s"
                     % (esc(", ".join(rs)), format(len(members_of(b)[b.group(start, 4)]), ","),
                        esc(node_name(b, m)), blk or
                        "<p class=mut>(its source line could not be confirmed)</p>"))
        if chain:
            cause = chain[-1]
            steps = " &rarr; ".join(esc(node_name(b, x)) for x in chain)
            blk = code_block(b, cause, "where this run's pointers end: the cause", 4, 3)
            extra = ("<p>Why Stava marks the parameter escaping, followed through this run's own "
                     "successor pointers: %s. The last node's own reasons: <code>%s</code>. Stava "
                     "decides a parameter once for every caller, so one caller's escape is every "
                     "caller's.</p>%s"
                     % (steps, esc(", ".join(sorted(b.own(cause) - PROP))), blk or
                        "<p class=mut>(its source line could not be confirmed)</p>"))
        secE.append("<h3>%s</h3>%s%s%s%s" % (b.name, lic, head, "".join(blocks), extra))

    summary = ["<h1>Escape claims: evidence from benchmark source</h1>",
               "<p class=mut>DaCapo 9.12-MR1, Stava with heapviz patches 0002 to 0006, "
               "MarkStoreEscaping=false, roots mode. Each code line is found through the "
               "LineNumberTable of the class file Stava analysed and shown from the upstream "
               "source release of the same version; <code>tools/source_check.py</code> checks that "
               "match. The highlighted line is the one the bytecode index maps to.</p>",
               "<div class=scroll><table class=sum><tr><th>benchmark</th><th>Stava nodes</th><th>allocation sites</th>"
               "<th>single-reason share</th><th>escaping sites through a parameter</th></tr>"]
    for n, nodes, sites, single, par in rows:
        summary.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%.1f %%</td><td>%.1f %%</td></tr>"
                       % (n, format(nodes, ","), format(sites, ","), single, par))
    summary.append("</table></div>")
    sections = [
        "<h2>A. Propagated reasons repeat a cause</h2><p>TRANSITIVE_SUCCESSOR and "
        "PARAM_ESCAPES_VIA_SUCCESSOR only say that something the object depends on escapes. In "
        "these examples the object already carries the reason that successor leads to.</p>"] + secA + [
        "<h2>B. One allocation, several nodes</h2><p>Stava makes a node for an object in every "
        "method that receives it as a call result or reads it from a field. The old figures counted "
        "each of these.</p>"] + secB + [
        "<h2>C. Inherited reasons</h2><p>The resolver escapes a whole strongly connected component "
        "at once, and the reasons were stamped on every member.</p>"] + secC + [
        "<h2>D. Escape through a shared parameter</h2><p>For each benchmark, its largest "
        "parameter hub and sites that escape through it. StringBuilder sites are string "
        "concatenations: javac compiles <code>a + b</code> to a builder.</p>"] + secE
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page(sections, "".join(summary)))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
