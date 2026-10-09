#!/usr/bin/env python3
"""
source_dashboard.py - a self-contained page pairing each escape reason with the code it fires in.

WHY THE "SOURCE" IS BYTECODE
  DaCapo ships jars, not sources: there is not one .java file anywhere under
  stava/benchmarks. What we do have is the exact class tree Stava analysed (the Tamiflex
  Play-Out dump), so this shows `javap -c -l` disassembly with the LineNumberTable folded in.

  For an escape site that is the better evidence anyway. The claim being checked is "MONITOR
  fired in this method", and the disassembly either contains a monitorenter or it does not.
  A source line would be one inference further away from the fact.

WHAT EACH ROW SHOWS
  allocation site   the object's own (method, bci). For `internal` that is the `new`; for
                    `external` the call or field load that produced the handle; for
                    `parameter` / `returnValue` the method declaration, because their bci is
                    an argument index or a constant 0 rather than an offset.
  escape site       where the reason fired. NOT recorded by Stava - record() takes no Unit -
                    so it is derived by locating the witnessing opcode. Three outcomes are
                    distinguished and none of them is silently smoothed over:
                      exact         one such opcode in the method
                      n candidates  several; the true one is unknown
                      inherited     none at all, so the reason came from a resolver component
                                    (Reason-Pipeline-Spec X-A4) and was never earned here
  code              the disassembly window around whichever offset is in question, with the
                    witnessing instruction marked.

INPUT
  the json written by extract/python/reason_source_map.py, plus the same class tree it used.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

OPCODE = re.compile(r"^\s*(\d+):\s+(\S+)")
WITNESS_OPS = {"monitorenter", "athrow", "putstatic", "getstatic", "ldc", "ldc_w", "ldc2_w"}


class Disasm:
    """Per-class {method: (instructions, linetable)} from one `javap -c -l` per class."""

    def __init__(self, classes_dir, java_home):
        self.dir, self.java_home, self.cache = classes_dir, java_home, {}

    def method(self, fqcn, mname):
        if fqcn not in self.cache:
            self.cache[fqcn] = self._load(fqcn)
        return self.cache[fqcn].get(mname)

    def _load(self, fqcn):
        exe = os.path.join(self.java_home, "bin", "javap") if self.java_home else "javap"
        try:
            r = subprocess.run([exe, "-p", "-c", "-l", "-classpath", self.dir, fqcn],
                               capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if r.returncode != 0:
            return {}
        out, cur, in_lines = {}, None, False
        simple = fqcn.rsplit(".", 1)[-1]
        for raw in r.stdout.splitlines():
            s = raw.strip()
            if s == "static {};":
                cur, in_lines = "<clinit>", False
                out.setdefault(cur, ([], []))
                continue
            if s.endswith(";") and "(" in s and not s.startswith("//"):
                toks = s[:-1].split("(", 1)[0].split()
                name = toks[-1] if toks else ""
                if len(toks) == 1 and (name == fqcn or name.endswith("." + simple)):
                    name = "<init>"
                cur, in_lines = name, False
                out.setdefault(cur, ([], []))
                continue
            if s == "LineNumberTable:":
                in_lines = True
                continue
            if in_lines:
                m = re.match(r"^\s*line (\d+): (\d+)$", raw)
                if m and cur:
                    out[cur][1].append((int(m.group(2)), int(m.group(1))))
                    continue
                in_lines = False
            m = OPCODE.match(raw)
            if m and cur:
                out[cur][0].append((int(m.group(1)), s))
        return out

    def window(self, fqcn, mname, want_ops=None, around=None, radius=6):
        got = self.method(fqcn, mname)
        if not got:
            return None, None
        instrs, table = got
        if not instrs:
            return None, None
        idx = None
        if want_ops:
            for i, (_off, txt) in enumerate(instrs):
                op = txt.split(":", 1)[1].strip().split()[0] if ":" in txt else ""
                if op in want_ops:
                    idx = i
                    break
        if idx is None and around is not None:
            best = None
            for i, (off, _t) in enumerate(instrs):
                if off <= around and (best is None or off > instrs[best][0]):
                    best = i
            idx = best
        if idx is None:
            idx = 0
        lo, hi = max(0, idx - radius), min(len(instrs), idx + radius + 1)
        return instrs[lo:hi], (instrs[idx][0], table)


def line_at(table, off):
    best = None
    for o, ln in sorted(table or ()):
        if o <= off:
            best = ln
        else:
            break
    return best


def esc(s):
    return html.escape(str(s), quote=True)


CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a1a;--mut:#6b6b6b;--line:#e3e3e0;--card:#fff;
 --acc:#0072B2;--warn:#D55E00;--ok:#009E73;--code:#f6f6f4}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:22px 28px;border-bottom:1px solid var(--line);background:var(--card)}
h1{margin:0 0 4px;font-size:19px;font-weight:640;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:12.5px}
main{display:grid;grid-template-columns:260px 1fr;gap:0;min-height:calc(100vh - 88px)}
nav{border-right:1px solid var(--line);background:var(--card);padding:14px 0;overflow-y:auto;
 max-height:calc(100vh - 88px);position:sticky;top:0}
nav button{display:block;width:100%;text-align:left;border:0;background:none;cursor:pointer;
 padding:7px 18px;font:inherit;color:var(--fg);border-left:3px solid transparent}
nav button:hover{background:#f2f2ef}
nav button.on{border-left-color:var(--acc);background:#eef5fb;font-weight:600}
nav .n{float:right;color:var(--mut);font-variant-numeric:tabular-nums;font-size:12px}
section{padding:20px 28px;overflow-x:auto}
.rh{display:flex;align-items:baseline;gap:14px;margin-bottom:4px}
.rh h2{margin:0;font-size:17px}
.tags{color:var(--mut);font-size:12.5px}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11.5px;margin-right:5px}
.t-ok{background:#e2f4ee;color:#04624a}
.t-amb{background:#fdf0e3;color:#8a4b06}
.t-inh{background:#fde8e4;color:#8c2c12}
.note{color:var(--mut);font-size:12.5px;margin:8px 0 16px;max-width:76ch}
.site{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:12px}
.site>summary{cursor:pointer;padding:10px 14px;display:grid;
 grid-template-columns:64px 1fr 1fr;gap:12px;align-items:baseline;font-size:13px}
.site>summary::-webkit-details-marker{display:none}
.cnt{font-variant-numeric:tabular-nums;font-weight:640;color:var(--acc)}
.loc{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arrow{color:var(--mut)}
.body{border-top:1px solid var(--line);padding:12px 14px;background:var(--code)}
pre{margin:6px 0 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
 line-height:1.5;overflow-x:auto}
.hit{background:#ffe9a8;font-weight:640;display:inline-block;width:100%}
.lbl{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;
 margin-top:10px}
.lbl:first-child{margin-top:0}
.miss{color:var(--mut);font-style:italic}
"""

JS = """
const btns=[...document.querySelectorAll('nav button')];
const secs=[...document.querySelectorAll('section')];
function show(id){
  btns.forEach(b=>b.classList.toggle('on',b.dataset.r===id));
  secs.forEach(s=>s.hidden=(s.dataset.r!==id));
}
btns.forEach(b=>b.onclick=()=>show(b.dataset.r));
if(btns.length)show(btns[0].dataset.r);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, help="json from reason_source_map.py")
    ap.add_argument("--classes", required=True)
    ap.add_argument("--java-home", default=os.environ.get("JAVA_HOME", ""))
    ap.add_argument("--out", required=True)
    ap.add_argument("--sites-per-reason", type=int, default=15)
    a = ap.parse_args()

    data = json.load(open(a.map, encoding="utf-8"))
    dis = Disasm(a.classes, a.java_home)
    meta = data["meta"]

    def code_block(sig_hint, want_ops, around, title):
        """sig_hint is 'Cls.java:NN' style - we need the real method, so use the raw fields."""
        return None

    nav, secs = [], []
    for r in data["reasons"]:
        rid = r["reason"]
        nav.append('<button data-r="%s">%s<span class="n">%d</span></button>'
                   % (esc(rid), esc(rid), r["objects"]))
        tags = []
        if r.get("witnessed") is not None:
            tags.append('<span class="tag t-ok">%d witnessed</span>' % r["witnessed"])
            tags.append('<span class="tag t-amb">%d ambiguous</span>' % (r.get("ambiguous") or 0))
            tags.append('<span class="tag t-inh">%d inherited</span>' % (r.get("unwitnessed") or 0))
        else:
            tags.append('<span class="tag t-amb">no single opcode &mdash; '
                        'escape site not derivable</span>')
        rows = []
        for site in r["sites"][:a.sites_per_reason]:
            al, es_, kind = site["allocSite"], site["escapeSite"], site.get("allocKind", "")
            m = re.match(r"^(.*?):(\d+)", es_ or "")
            body = []
            src = site.get("methodSig") or ""
            cls = site.get("cls")
            mname = site.get("mname")
            body.append('<div class="lbl">allocation site &mdash; %s</div>' % esc(kind))
            if cls and mname:
                w, info = dis.window(cls, mname, None, site.get("bciInt"), 5)
                if w:
                    body.append(render_window(w, info, None))
                else:
                    body.append('<div class="miss">no disassembly for %s.%s</div>'
                                % (esc(cls), esc(mname)))
            else:
                body.append('<div class="miss">%s</div>' % esc(al))
            body.append('<div class="lbl">escape site</div>')
            if cls and mname and "NONE IN METHOD" not in es_ and "n/a" not in es_:
                w, info = dis.window(cls, mname, WITNESS_OPS, None, 5)
                if w:
                    body.append(render_window(w, info, WITNESS_OPS))
                else:
                    body.append('<div class="miss">%s</div>' % esc(es_))
            else:
                body.append('<div class="miss">%s</div>' % esc(es_))
            rows.append(
                '<details class="site"><summary><span class="cnt">%d</span>'
                '<span class="loc">%s</span>'
                '<span class="loc"><span class="arrow">&rarr;</span> %s</span></summary>'
                '<div class="body">%s</div></details>'
                % (site["objects"], esc(al), esc(es_), "".join(body)))
        secs.append(
            '<section data-r="%s" hidden><div class="rh"><h2>%s</h2>'
            '<span class="tags">%d objects &middot; %d distinct site pairs</span></div>'
            '<div>%s</div><p class="note">%s</p>%s</section>'
            % (esc(rid), esc(rid), r["objects"], r["distinctSites"], "".join(tags),
               esc(meta.get("escapeSite", "")), "".join(rows) or
               '<p class="miss">no sites</p>'))

    doc = (
        "<title>%s &mdash; escape reasons in code</title><style>%s</style>"
        "<header><h1>%s &mdash; escape reasons in code</h1>"
        "<div class='sub'>%d application objects &middot; source is <code>javap -c -l</code> "
        "disassembly: DaCapo ships no .java. %s</div></header>"
        "<main><nav>%s</nav>%s</main><script>%s</script>"
        % (esc(meta["label"]), CSS, esc(meta["label"]), meta["objects"],
           esc("Restricted to reason sets universal across all six benchmarks."
               if meta.get("onlySets") else ""),
           "".join(nav), "".join(secs), JS))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("wrote %s (%.1f KB)" % (a.out, os.path.getsize(a.out) / 1024.0))


def render_window(instrs, info, want_ops):
    off_hit, table = info if info else (None, None)
    out = []
    for off, txt in instrs:
        ln = line_at(table, off)
        op = txt.split(":", 1)[1].strip().split()[0] if ":" in txt else ""
        hit = (want_ops and op in want_ops) or (not want_ops and off == off_hit)
        row = "%5s  %s" % ("L%d" % ln if ln else "", txt)
        out.append('<span class="hit">%s</span>' % esc(row) if hit else esc(row))
    return "<pre>%s</pre>" % "\n".join(out)


if __name__ == "__main__":
    main()
