#!/usr/bin/env python3
"""
graph_to_html.py — graph-full.json -> a self-contained, pannable HTML explorer.

This is the INTERACTIVE tool of PTA-Task-List task 13, deliberately separate from
render/python/graph_to_svg.py which makes the static report figures. Task 13 is explicit that these
are different tools and one artefact should not try to be both, so they share the graph.json
interface and nothing else.

Why focus-and-expand rather than one big picture: avrora's application-only graph is 11k nodes
and 24k edges. Drawing it at once produces a hairball that answers no question. The explorer
starts at one method and expands outward by hops, which is how you actually read a PTG.

Colour still means exactly one thing PER VIEW, and each view says which thing in its own
legend. In the two graph views colour is equi-escape set, as before, and edge style is
provenance. In the reason-set cluster view added in Phase 11 there are no equi-escape sets on
screen at all, so colour there is the number of escape reasons, on an ordered sequential scale.
The legend is swapped with the view, so the two encodings are never on screen together.

THE REASON-SET CLUSTER VIEW (Phase 11 figure 1)
  One square per DISTINCT escape-reason set, square AREA proportional to the number of objects
  carrying exactly that set, ordered by reason count then size, top N individually and the rest
  in one aggregated square whose count is shown. A red hatch marks any set containing a reason
  that is not a known program cause: a surrender (Stava gave up) or an unresolved successor
  chain (SUCCESSOR_*, roots mode). Each reason is labelled with which of the two it is.
  It lives here rather than in render/python/reason_figures.py for avrora specifically: at 6k objects
  the tail of distinct sets is long and a static figure cannot carry the drill-down from a
  cluster to its members, which is the only reason to look at it.

USAGE
  python3 render/python/graph_to_html.py --graph build/out/avrora/graph-full.json \\
      --title "avrora — PTG explorer" --out render/figures/avrora-explorer.html
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extract", "python"))
from info_to_graph import SURRENDER, REASONS_GAP  # noqa: E402

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg:#ffffff; --fg:#111; --muted:#666; --line:#ddd; --panel:#fafafa;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; font:13px/1.45 Helvetica,Arial,sans-serif; color:var(--fg); background:var(--bg); }
  #wrap { display:flex; height:100vh; }
  #side { width:340px; flex:0 0 340px; border-right:1px solid var(--line); display:flex; flex-direction:column; background:var(--panel); }
  #main { flex:1; position:relative; overflow:hidden; }
  h1 { font-size:15px; margin:0 0 4px; }
  .sub { font-size:11px; color:var(--muted); }
  #side header { padding:12px 14px; border-bottom:1px solid var(--line); }
  #controls { padding:10px 14px; border-bottom:1px solid var(--line); }
  #controls label { display:block; margin:6px 0 2px; font-size:11px; color:var(--muted); }
  input[type=search], select { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:4px; font:inherit; background:#fff; }
  .chk { display:flex; align-items:center; gap:6px; margin:3px 0; font-size:12px; }
  .chk span.sw { width:26px; height:0; border-top-width:2px; display:inline-block; }
  #results { flex:1; overflow:auto; }
  .row { padding:6px 14px; border-bottom:1px solid #eee; cursor:pointer; font-size:12px; }
  .row:hover { background:#eef4fb; }
  .row .m { color:var(--muted); font-size:11px; word-break:break-all; }
  #cv { width:100%; height:100%; cursor:grab; display:block; }
  #cv.drag { cursor:grabbing; }
  /* Both overlays sit on the LEFT, so fit() reserves a gutter that clears them and starts the
     graph to their right. Capping their width bounds that gutter — an uncapped 640px HUD next
     to a wide legend would have eaten most of the pane. */
  #hud { position:absolute; left:12px; top:12px; background:rgba(255,255,255,.94); border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:11px; max-width:360px; max-height:46vh; overflow:auto; }
  #legend { position:absolute; left:12px; bottom:12px; background:rgba(255,255,255,.94); border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:11px; max-width:360px; max-height:40vh; overflow:auto; }
  #legend b { display:block; margin-bottom:4px; }
  .lg { display:flex; align-items:center; gap:6px; margin:2px 0; }
  .sw2 { width:14px; height:14px; border-radius:3px; border:1px solid #222; display:inline-block; }
  button { font:inherit; padding:4px 8px; border:1px solid var(--line); background:#fff; border-radius:4px; cursor:pointer; }
  #zoomers { position:absolute; right:12px; top:12px; display:flex; gap:6px; }
  .note { padding:8px 14px; font-size:11px; color:var(--muted); border-top:1px solid var(--line); }
  /* the opened cluster's set, named in full: the label under a square is clipped to the
     square's width and a six-reason set never fits inside one. */
  .setbox { padding:8px 14px 10px; border-bottom:1px solid var(--line); background:#f2f6fb; }
  .seths { font-size:11px; color:var(--muted); margin-bottom:5px; }
  .rsn { font-size:12px; font-family:ui-monospace,Consolas,monospace; padding:1px 0 1px 10px;
         border-left:3px solid #4292c6; margin:2px 0; word-break:break-all; }
  .rsn.surr { border-left-color:#b00; color:#b00; }
  .rsn em { font-style:normal; font-size:10px; color:#b00; }
  /* Isolation. A dense method draws as a solid mat of curves; fading everything but the
     pointed-at edge is the only thing that makes a single one followable. */
  #scene.iso .ed:not(.hot) .wire { opacity:.05; }
  #scene.iso .ed:not(.hot) text  { opacity:0; }
  #scene.iso .nd:not(.hot)       { opacity:.13; }
  #scene .ed.hot .wire { stroke-width:4.5; }
  #scene .ed.hot text  { font-weight:bold; }
  #scene.iso .nd.hot rect { stroke-width:3; }
</style>
<div id="wrap">
  <div id="side">
    <header>
      <h1>__TITLE__</h1>
      <div class="sub" id="meta"></div>
    </header>
    <div id="controls">
      <label>Search methods, classes, objects</label>
      <input type="search" id="q" placeholder="e.g. PinRegister, Simulator, decode_">
      <label>Mode</label>
      <select id="mode">
        <option value="method">Whole method (all its objects + edges)</option>
        <option value="hops">Neighbourhood around one object</option>
        <option value="reasonset">Reason-set clusters (all objects)</option>
      </select>
      <div class="chk" id="topwrap" style="margin-top:6px">top
        <select id="top" style="width:auto"><option>10</option><option selected>20</option><option>40</option><option>200</option></select>
        reason sets drawn individually, rest aggregated</div>
      <div class="chk" style="margin-top:6px"><input type="checkbox" id="follow"> follow calls out of the method (adds callee nodes)</div>
      <label>Colour nodes by</label>
      <select id="cby">
        <option value="s">equi-escape set (definition S)</option>
        <option value="reasons">number of escape reasons</option>
        <option value="cluster">escape-reason set (cluster)</option>
      </select>
      <div class="chk" style="margin-top:6px"><input type="checkbox" id="trace"> trace contributors: highlight everything whose escaping feeds the hovered object</div>
      <label>Hops (neighbourhood mode)</label>
      <select id="hops"><option>1</option><option selected>2</option><option>3</option></select>
      <label>Edge kinds — PTG <code>Fields:</code> map (solid)</label>
      <div class="chk"><input type="checkbox" id="e_CONTAINMENT" checked><span class="sw" style="border-top:3px solid #1a1a1a"></span> CONTAINMENT — <code>a.f = b</code></div>
      <div class="chk"><input type="checkbox" id="e_FIELD_LOAD" checked><span class="sw" style="border-top:3px solid #009E73"></span> FIELD_LOAD — <code>a = b.f</code></div>
      <label>Edge kinds — summary dependencies (dashed)</label>
      <div class="chk"><input type="checkbox" id="e_ARGUMENT" checked><span class="sw" style="border-top:2px dashed #444"></span> ARGUMENT — passed to a callee</div>
      <div class="chk"><input type="checkbox" id="e_RETURN" checked><span class="sw" style="border-top:2px dotted #7a4fa3"></span> RETURN — returned</div>
      <div class="note" style="padding:6px 0 0;border:0">Both solid kinds come from the <em>same</em> <code>Fields:</code> map — Stava does not distinguish them. The split is inferred here from the target's object type. Click any edge for detail.</div>
    </div>
    <div id="results"></div>
    <div class="note" id="note"></div>
  </div>
  <div id="main">
    <svg id="cv"></svg>
    <div id="hud"></div>
    <div id="zoomers">
      <button id="zin">+</button><button id="zout">−</button><button id="zfit">fit</button>
    </div>
    <div id="legend"><b id="lgtitle">Colour = equi-escape set (definition S). Nothing else is coloured.</b>
      <div id="setlg"></div>
      <div id="graphlg">
        <div class="lg" style="margin-top:5px"><span style="width:14px;height:14px;border:1px dashed #777;display:inline-block;border-radius:3px"></span> dashed outline = parameter / return node, not an allocation</div>
        <div class="lg"><span style="width:14px;height:14px;border:2px solid #b00;display:inline-block;border-radius:3px"></span> red outline = library boundary (callee outside the filter)</div>
      </div>
      <div id="reasonlg" style="display:none">
        <div id="seqlg" class="lg"></div>
        <div class="lg" style="margin-top:5px"><span style="width:14px;height:14px;border:2px solid #b00;background:#e8e8e8;display:inline-block;border-radius:3px"></span> red hatched outline = the set contains a reason that is not a known program cause: a surrender (Stava gave up) or an unresolved successor chain (SUCCESSOR_*)</div>
        <div class="lg"><span style="width:14px;height:14px;border:1px solid #222;background:repeating-linear-gradient(180deg,#222 0 1.3px,#e8e8e8 1.3px 5px);display:inline-block;border-radius:3px"></span> horizontal stripes = the share of the set's objects carrying a reason inherited from their resolver component (fired on another member); shown only for runs made with patch 0005</div>
        <div class="lg"><span style="width:14px;height:14px;border:1px solid #222;background:#e8e8e8;display:inline-block;border-radius:3px"></span> grey = the aggregated "other" square; its member count is shown and is never dropped</div>
        <div class="lg">Square AREA is proportional to member count. Big number = reasons in the set, small number = objects.</div>
      </div>
    </div>
  </div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
// The payload is interned: node ids are integer indices, and method signatures, escape
// statuses, provenances and field names live in string tables. A 60-character node id
// repeated twice per edge across 24k edges is most of the raw file; interning takes the page
// from 9.1 MB to well under 2 MB, which is the difference between it opening and not.
const P = JSON.parse(document.getElementById('data').textContent);
const G = {
  meta: P.meta,
  nodes: P.nodes.map((a, i) => ({
    id: i, label: a[0], method: P.methods[a[1]], kind: a[2] ? 'param' : 'object',
    s: a[3] === -1 ? null : a[3], escapeStatus: a[4] === -1 ? null : P.statuses[a[4]],
    libraryBoundary: !!a[5],
    // a[6] indexes P.reasonsets. -1 means the run carried no .reasons file at all, which is
    // NOT the same as an empty set and must not be drawn as the zero bucket.
    rs: (a.length > 6 && a[6] !== -1) ? P.reasonsets[a[6]] : null,
    // a[7] (patch 0005) indexes the object's OWN reasons; null = this run records no split
    own: (a.length > 7 && a[7] !== -1) ? P.reasonsets[a[7]] : null
  })),
  edges: P.edges.map(a => ({
    f: a[0], t: a[1], p: P.provs[a[2]], lab: a[3] === -1 ? "" : P.labels[a[3]]
  }))
};
const NODES = {}; G.nodes.forEach(n => NODES[n.id] = n);
const OUT = {}, IN = {};
G.edges.forEach(e => { (OUT[e.f] ||= []).push(e); (IN[e.t] ||= []).push(e); });

const PALETTE = ["#56B4E9","#E69F00","#009E73","#CC79A7","#0072B2","#D55E00","#F0E442","#999999"];
// SOLID = an edge in the PTG's Fields: map (a real heap edge). DASHED = an edge derived from
// a method summary (an interprocedural obligation, not a heap link). Within each family the
// distinction is carried by HUE, not by dash pattern, because two dash patterns on curves of
// similar colour are near-impossible to tell apart at any zoom.
const STYLE = {
  CONTAINMENT: {c:"#1a1a1a", w:2.4, d:"",    fam:"PTG Fields: map"},
  FIELD_LOAD:  {c:"#009E73", w:2.0, d:"",    fam:"PTG Fields: map"},
  ARGUMENT:    {c:"#444444", w:1.3, d:"7,4", fam:"method summary"},
  RETURN:      {c:"#7a4fa3", w:1.4, d:"2,3", fam:"method summary"},
};
// Shown when an edge is clicked. The FIELD_LOAD wording is deliberate: see the note on
// graph-full.json's provenance below and in extract/python/benchmark_scale.py.
const EDGE_DOC = {
  CONTAINMENT: "a.f = b — a field STORE. b really is reachable from a.",
  FIELD_LOAD:  "a = b.f — a field READ. The target is a fresh placeholder standing for "
             + "whatever b.f points at; it is NOT an object known to be inside b.",
  ARGUMENT:    "b is passed to a callee as its receiver or an argument.",
  RETURN:      "b is returned from the callee.",
};
const NW=234, NH=44, HG=46, VG=142, CAP=420;

// ---- reason-set cluster view ---------------------------------------------------
// ColorBrewer Blues: SEQUENTIAL, because reason count is ordered. The categorical PALETTE
// above would imply the counts are unordered labels.
const SEQ = ["#f7fbff","#deebf7","#c6dbef","#9ecae1","#6baed6","#4292c6","#2171b5","#08519c","#08306b"];
const SURRENDER = new Set(P.surrender || []);
const GAP_REASONS = new Set(P.gap || []);
const notCauseLabel = r => GAP_REASONS.has(r) ? 'unresolved chain' : 'surrender';
const HAS_REASONS = G.nodes.some(n => n.rs !== null);
// reasons stamped on the object by its resolver component rather than fired on it
G.nodes.forEach(n => { n.inh = (n.rs && n.own) ? n.rs.filter(r => !n.own.includes(r)) : null; });
const HAS_SPLIT = G.nodes.some(n => n.kind === 'object' && n.own !== null);
const INH_NOTE = "inherited = fired on another member of the object's resolver component, which Stava escapes as a whole";
function seqFill(k, kmax) {
  if (k === null) return "#e8e8e8";
  if (kmax <= 0) return SEQ[0];
  const i = Math.round((SEQ.length-1) * (k/kmax));
  return SEQ[Math.max(0, Math.min(SEQ.length-1, i))];
}
function seqFg(f) { return SEQ.indexOf(f) >= 6 ? "#fff" : "#111"; }

// One entry per DISTINCT reason set over the object nodes, plus the member ids so a cluster
// can be drilled into. Built once; it does not depend on the edge filters.
const REASON_CLUSTERS = (() => {
  const m = new Map();
  G.nodes.forEach(n => {
    if (n.kind !== 'object' || n.rs === null) return;
    const k = n.rs.join(",");
    if (!m.has(k)) m.set(k, {reasons:n.rs, count:0, members:[], inherited:0,
                            hasSurrender:n.rs.some(r => SURRENDER.has(r))});
    const e = m.get(k); e.count++; e.members.push(n.id);
    if (n.inh && n.inh.length) e.inherited++;
  });
  return [...m.values()];
})();
// The full, unabbreviated name of a cluster's set. The label under a square is clipped to the
// square's width and a six-reason set never fits, so this is what the tooltip, the HUD and the
// member-list header all use instead.
function setLabel(c) {
  if (c.reasons === null) return 'other — ' + c.distinctSets + ' further sets';
  if (!c.reasons.length) return 'no reason — does not escape';
  return c.reasons.join(' + ');
}
// Node colour. The repo rule is that colour carries exactly ONE meaning; here it carries one
// meaning AT A TIME, chosen by the "Colour nodes by" control, and the legend is rewritten to
// match on every change so the two are never out of step.
const RS_MAX = Math.max(0, ...G.nodes.map(n => n.rs ? n.rs.length : 0));
const CLUSTER_OF = (() => {
  const m = {};
  REASON_CLUSTERS.slice().sort((a,b)=>b.count-a.count).forEach((c,i) => { m[c.reasons.join(',')] = i; });
  return m;
})();
// Denominator for every percentage in this view: objects that carry reason data at all,
// including those with the empty set. Same convention as figure 2, so a share quoted here and
// a share read off the multiplicity histogram mean the same thing.
const RS_TOTAL = G.nodes.filter(n => n.kind === 'object' && n.rs !== null).length;
function pct(n) {
  if (!RS_TOTAL) return "";
  const p = 100 * n / RS_TOTAL;
  return (p >= 10 ? p.toFixed(0) : p.toFixed(1)) + "%";
}
function colourBy() { const e=document.getElementById('cby'); return e ? e.value : 's'; }
function nodeFill(n) {
  const mode = colourBy();
  if (mode === 'reasons') return n.rs === null ? "#f4f4f4" : seqFill(n.rs.length, RS_MAX);
  if (mode === 'cluster') {
    if (n.rs === null) return "#f4f4f4";
    const ci = CLUSTER_OF[n.rs.join(',')];
    return ci === undefined || ci >= PALETTE.length ? "#cccccc" : PALETTE[ci % PALETTE.length];
  }
  return n.s != null ? PALETTE[n.s % PALETTE.length] : "#f4f4f4";
}
function clustersToDraw() {
  const top = +document.getElementById('top').value;
  const byPop = REASON_CLUSTERS.slice().sort((a,b) =>
    b.count-a.count || a.reasons.length-b.reasons.length || a.reasons.join().localeCompare(b.reasons.join()));
  const keep = byPop.slice(0, top), tail = byPop.slice(top);
  keep.sort((a,b) => a.reasons.length-b.reasons.length || b.count-a.count ||
                     a.reasons.join().localeCompare(b.reasons.join()));
  const out = keep.slice();
  if (tail.length) out.push({reasons:null, count:tail.reduce((s,e)=>s+e.count,0),
                             distinctSets:tail.length, members:[].concat(...tail.map(e=>e.members)),
                             inherited:tail.reduce((s,e)=>s+e.inherited,0),
                             hasSurrender:tail.some(e=>e.hasSurrender)});
  return out;
}

document.getElementById('meta').textContent =
  G.meta.benchmark + " · " + G.meta.jdk + " · " + G.meta.config;
document.getElementById('note').textContent =
  G.nodes.length.toLocaleString() + " nodes, " + G.edges.length.toLocaleString() +
  " edges in the filtered application graph. " + (G.meta.filter||"") +
  (G.meta.reasons ? " · Reasons: " + G.meta.reasons : "");

// The set legend is built by setLegend(), which rebuilds it on every colour-by change so the
// swatches can never describe a colouring that is no longer on screen.

// ---- method index -------------------------------------------------------------
const METHODS = {};
G.nodes.forEach(n => { if (n.method) (METHODS[n.method] ||= []).push(n.id); });
// Rank methods by edges that stay INSIDE the method - that is the method's own PTG, and it
// is what makes a readable view. Ranking by total edges puts hot dispatchers with 1500
// outgoing ARGUMENT edges at the top, which are the least readable graphs in the program.
const METHOD_EDGES = {}, METHOD_INNER = {};
G.edges.forEach(e => {
  const mf = (NODES[e.f]||{}).method, mt = (NODES[e.t]||{}).method;
  if (mf) METHOD_EDGES[mf] = (METHOD_EDGES[mf]||0) + 1;
  if (mf && mf === mt) METHOD_INNER[mf] = (METHOD_INNER[mf]||0) + 1;
});
const METHOD_LIST = Object.keys(METHODS).sort((a,b) =>
  (METHOD_INNER[b]||0)-(METHOD_INNER[a]||0) || (METHOD_EDGES[b]||0)-(METHOD_EDGES[a]||0));

function activeKinds() {
  return new Set(["CONTAINMENT","FIELD_LOAD","ARGUMENT","RETURN"]
    .filter(k => document.getElementById('e_'+k).checked));
}

// ---- search -------------------------------------------------------------------
function renderResults() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const mode = document.getElementById('mode').value;
  const box = document.getElementById('results');
  let items;
  if (mode === 'reasonset') {
    const cs = clustersToDraw();
    items = cs.filter(c => !q || (c.reasons||["other"]).join(",").toLowerCase().includes(q))
      .map((c,i) => ({key:"rs:"+i,
                      main:(c.reasons === null ? "other ("+c.distinctSets+" sets)"
                            : (c.reasons.length ? c.reasons.join(" + ") : "no reason — does not escape")),
                      sub:c.count+" objects ("+pct(c.count)+") · "+(c.reasons===null?"mixed":c.reasons.length)+" reasons"
                          +(HAS_SPLIT?" · "+c.inherited+" inherited":"")
                          +(c.hasSurrender?" · contains surrender / unresolved chain":""),
                      cls:""}));
  } else if (mode === 'method') {
    items = METHOD_LIST.filter(m => !q || m.toLowerCase().includes(q)).slice(0, 300)
      .map(m => ({key:m, main:m.replace(/^<|>$/g,'').split(':').slice(1).join(':').trim(),
                  sub:(METHODS[m].length)+" objects · "+(METHOD_INNER[m]||0)+" edges inside · "
                      +(METHOD_EDGES[m]||0)+" total", cls:m}));
  } else {
    items = G.nodes.filter(n => n.kind === 'object' && (!q || n.label.toLowerCase().includes(q)
              || (n.method||'').toLowerCase().includes(q))).slice(0, 300)
      .map(n => ({key:n.id, main:n.label, sub:n.escapeStatus || 'unresolved', cls:n.method}));
  }
  box.innerHTML = items.map(i =>
    `<div class="row" data-k="${encodeURIComponent(i.key)}"><div>${esc(i.main)}</div>
     <div class="m">${esc(i.sub)}</div></div>`).join("") ||
    '<div class="row"><em>no match</em></div>';
  box.querySelectorAll('.row[data-k]').forEach(r =>
    r.onclick = () => show(decodeURIComponent(r.dataset.k)));
}
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// ---- build the subgraph to draw ------------------------------------------------
function subgraph(key) {
  const kinds = activeKinds();
  const mode = document.getElementById('mode').value;
  let keep = new Set();
  if (mode === 'method') {
    (METHODS[key]||[]).forEach(i => keep.add(i));
    // Following every outgoing edge is off by default: a hot method has >1000 ARGUMENT
    // edges and pulling in each callee parameter buries the method's own PTG in a hairball.
    if (document.getElementById('follow').checked) {
      const own = new Set(keep);
      G.edges.forEach(e => { if (kinds.has(e.p) && own.has(e.f)) keep.add(e.t); });
    }
  } else {
    const hops = +document.getElementById('hops').value;
    let frontier = new Set([key]); keep.add(key);
    for (let h=0; h<hops; h++) {
      const nxt = new Set();
      frontier.forEach(i => {
        (OUT[i]||[]).forEach(e => { if (kinds.has(e.p) && !keep.has(e.t)) { keep.add(e.t); nxt.add(e.t); } });
        (IN[i]||[]).forEach(e => { if (kinds.has(e.p) && !keep.has(e.f)) { keep.add(e.f); nxt.add(e.f); } });
      });
      frontier = nxt;
      if (keep.size > CAP) break;
    }
  }
  let truncated = false;
  if (keep.size > CAP) { keep = new Set([...keep].slice(0, CAP)); truncated = true; }
  const edges = G.edges.filter(e => kinds.has(e.p) && keep.has(e.f) && keep.has(e.t));
  return {nodes:[...keep].map(i=>NODES[i]).filter(Boolean), edges, truncated};
}

// ---- layout: rank by hop distance over the drawn edges -------------------------
function layout(sg, root) {
  const adj = {}; sg.edges.forEach(e => (adj[e.f] ||= []).push(e.t));
  const ids = sg.nodes.map(n=>n.id), idset = new Set(ids);
  const indeg = {}; ids.forEach(i => indeg[i]=0);
  sg.edges.forEach(e => { if (e.f!==e.t) indeg[e.t] = (indeg[e.t]||0)+1; });
  let roots = root && idset.has(root) ? [root] : ids.filter(i => indeg[i]===0);
  if (!roots.length) roots = ids.slice(0,1);
  const depth = {}; roots.forEach(r => depth[r]=0);
  const queue = [...roots];
  while (queue.length) {
    const v = queue.shift();
    (adj[v]||[]).forEach(w => { if (depth[w]===undefined) { depth[w]=depth[v]+1; queue.push(w); } });
  }
  let maxd = 0; ids.forEach(i => { if (depth[i]===undefined) depth[i] = 0; maxd=Math.max(maxd,depth[i]); });
  const rows = {};
  ids.forEach(i => (rows[depth[i]] ||= []).push(i));
  const PER = 7, pos = {};
  let r = 0, widest = 0;
  const laid = [];
  const depths = Object.keys(rows).map(Number).sort((a,b)=>a-b);
  depths.forEach(d => rows[d].sort());

  // Crossing reduction: order each rank by the mean position of its neighbours in the rank
  // above (the standard barycentre heuristic, two downward sweeps). Ordering rows by node id
  // — which is what this did before — is an arbitrary order, and arbitrary orders cross a
  // lot. Two sweeps get most of the available improvement; more has diminishing returns and
  // this runs on every redraw.
  const predsOf = {};
  sg.edges.forEach(e => { if (e.f!==e.t) (predsOf[e.t] ||= []).push(e.f); });
  for (let sweep=0; sweep<2; sweep++) {
    const idx = {};
    depths.forEach(d => rows[d].forEach((id,i) => idx[id]=i));
    depths.slice(1).forEach(d => {
      const bary = {};
      rows[d].forEach((id,i) => {
        const ps = (predsOf[id]||[]).map(p => idx[p]).filter(v => v!==undefined);
        bary[id] = ps.length ? ps.reduce((a,b)=>a+b,0)/ps.length : i;
      });
      rows[d].sort((a,b) => bary[a]-bary[b] || (a<b?-1:1));
    });
  }
  depths.forEach(d => {
    const arr = rows[d];
    for (let i=0;i<arr.length;i+=PER) { laid.push(arr.slice(i,i+PER)); }
  });
  laid.forEach(a => widest = Math.max(widest, a.length));
  const totalW = widest*NW + (widest-1)*HG;
  laid.forEach((arr, ri) => {
    const w = arr.length*NW + (arr.length-1)*HG, x0 = (totalW-w)/2;
    arr.forEach((id,ci) => pos[id] = [x0 + ci*(NW+HG), ri*(NH+VG)]);
  });
  return {pos, w:totalW, h:laid.length*(NH+VG)};
}

// ---- draw ----------------------------------------------------------------------
const cv = document.getElementById('cv');
let view = {x:60, y:60, k:1};
let current = null;

function setLegend(mode, kmax) {
  const isRS = mode === 'reasonset';
  document.getElementById('graphlg').style.display = isRS ? 'none' : '';
  document.getElementById('reasonlg').style.display = isRS ? '' : 'none';
  document.getElementById('setlg').style.display = isRS ? 'none' : '';
  document.getElementById('topwrap').style.display = isRS ? '' : 'none';
  const CBY_TITLE = {
    s: "Colour = equi-escape set (definition S). Nothing else is coloured.",
    reasons: "Colour = number of escape reasons, on an ordered sequential scale. Nothing else is coloured.",
    cluster: "Colour = which escape-reason SET the object is in. Nothing else is coloured."
  };
  document.getElementById('lgtitle').textContent = isRS
    ? "Colour = number of escape reasons, on an ordered sequential scale. Nothing else is coloured."
    : CBY_TITLE[colourBy()];
  // The set-id swatches only describe definition S; under the other two colourings they would
  // be describing a scale that is no longer on screen.
  if (!isRS) {
    const lg = document.getElementById('setlg'), cb = colourBy();
    if (cb === 's') {
      const seen = new Map();
      G.nodes.forEach(n => { if (n.s != null && !seen.has(n.s)) seen.set(n.s, n.escapeStatus); });
      lg.innerHTML = [...seen.entries()].sort((a,b)=>a[0]-b[0])
        .map(([s,st]) => `<div class="lg"><span class="sw2" style="background:${PALETTE[s%PALETTE.length]}"></span> set ${s} · ${st}</div>`).join("");
    } else if (cb === 'reasons') {
      let h = "";
      for (let k=0;k<=RS_MAX;k++)
        h += `<span class="sw2" style="background:${seqFill(k,RS_MAX)};margin-right:3px"></span>${k}&nbsp;&nbsp;`;
      lg.innerHTML = `<div class="lg">${h||'(no reason data)'}</div>`;
    } else {
      const top = REASON_CLUSTERS.slice().sort((a,b)=>b.count-a.count).slice(0, PALETTE.length);
      lg.innerHTML = top.map((c,i) =>
        `<div class="lg"><span class="sw2" style="background:${PALETTE[i%PALETTE.length]}"></span>`
        + `${esc(clip(c.reasons.length?c.reasons.join(" + "):"no reason", 40))} · ${c.count} (${pct(c.count)})</div>`).join("")
        + `<div class="lg"><span class="sw2" style="background:#cccccc"></span>every other set</div>`;
    }
  }
  if (isRS) {
    let h = "";
    for (let k=0; k<=kmax; k++)
      h += `<span class="sw2" style="background:${seqFill(k,kmax)};margin-right:3px"></span>${k}&nbsp;&nbsp;`;
    document.getElementById('seqlg').innerHTML = h || "(no reason data)";
  }
}

// Figure 1. Squares, side proportional to sqrt(count) so AREA is proportional to member
// count — which is what the figure claims. Not a squarified treemap: the treemap's varying
// aspect ratios are exactly what makes its areas hard to compare, and comparing areas is the
// entire job here.
// keepView: redraw only to move the selection highlight. Leaves the HUD and the current
// zoom/pan alone, so clicking a square does not yank the canvas back to a fitted view.
function showClusters(keepView) {
  const cs = clustersToDraw();
  setLegend('reasonset', Math.max(0, ...cs.filter(c=>c.reasons).map(c=>c.reasons.length)));
  if (!cs.length) {
    cv.innerHTML = "";
    document.getElementById('hud').innerHTML =
      "<b>No reason data in this graph.</b><br>It was produced from a run with no .reasons "
      + "file, i.e. by an uninstrumented Stava.";
    return;
  }
  const kmax = Math.max(0, ...cs.filter(c=>c.reasons).map(c=>c.reasons.length));
  const maxc = Math.max(...cs.map(c=>c.count));
  const SMAX=150, SMIN=30, ROWW=1180, GAPX=16;
  const side = c => SMIN + (SMAX-SMIN)*Math.sqrt(c/maxc);
  const rows=[]; let cur=[], w=0;
  cs.forEach(c => { const s=side(c.count);
    if (cur.length && w+s+GAPX > ROWW) { rows.push(cur); cur=[]; w=0; }
    cur.push([c,s]); w+=s+GAPX; });
  if (cur.length) rows.push(cur);

  const parts=[`<defs><pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="7" stroke="#b00" stroke-width="2.4"/></pattern><pattern id="inherit" width="6" height="5" patternUnits="userSpaceOnUse"><rect width="6" height="5" fill="#ffffff" fill-opacity="0.55"/><line x1="0" y1="1" x2="6" y2="1" stroke="#222" stroke-width="1.3"/></pattern></defs>`,
               `<g id="scene">`];
  let y=0, totalW=0;
  rows.forEach(r => {
    let x=0; const rh=Math.max(...r.map(([,s])=>s))+34;
    r.forEach(([c,s]) => {
      const fill = c.reasons===null ? "#e8e8e8" : seqFill(c.reasons.length, kmax);
      const sel = current === "rs:"+cs.indexOf(c);
      parts.push(`<g class="cl" data-k="${encodeURIComponent("rs:"+cs.indexOf(c))}" style="cursor:pointer">
        <title>${esc(setLabel(c))}\n${c.count} object${c.count===1?"":"s"} (${pct(c.count)} of ${RS_TOTAL})${HAS_SPLIT?"\\n"+c.inherited+" carry an inherited reason (striped share)":""}</title>
        <rect x="${x}" y="${y}" width="${s}" height="${s}" rx="4" fill="${fill}" stroke="${sel?"#111":"#222"}" stroke-width="${sel?4:1.2}"/>
        ${c.hasSurrender?`<rect x="${x}" y="${y}" width="${s}" height="${s}" rx="4" fill="url(#hatch)" stroke="#b00" stroke-width="2.4"/>`:""}
        ${HAS_SPLIT && c.inherited ? `<rect x="${x+1}" y="${y+1}" width="${s-2}" height="${(s-2)*c.inherited/c.count}" fill="url(#inherit)"/>` : ""}
        <text x="${x+s/2}" y="${y+s/2-2}" font-size="15" font-weight="bold" text-anchor="middle" fill="${c.reasons===null?"#111":seqFg(fill)}">${c.reasons===null?"mix":c.reasons.length}</text>
        <text x="${x+s/2}" y="${y+s/2+14}" font-size="11" text-anchor="middle" fill="${c.reasons===null?"#111":seqFg(fill)}">${c.count}</text>
        <text x="${x+s/2}" y="${y+s/2+26}" font-size="9.5" text-anchor="middle" fill="${c.reasons===null?"#444":seqFg(fill)}" opacity="0.85">${pct(c.count)}</text>
        <text x="${x+s/2}" y="${y+s+13}" font-size="9.5" text-anchor="middle" fill="#444">${esc(clip(c.reasons===null?("other · "+c.distinctSets+" sets"):(c.reasons.length?c.reasons.join("+"):"no reason"), Math.max(8, Math.floor(s/5.6))))}</text>
      </g>`);
      x += s+GAPX;
    });
    totalW=Math.max(totalW,x); y+=rh;
  });
  parts.push(`</g>`);
  cv.innerHTML = parts.join("");
  cv.querySelectorAll('.cl').forEach(g => g.onclick = () => show(decodeURIComponent(g.dataset.k)));
  if (keepView) { apply(); return; }
  const other = cs.find(c=>c.reasons===null);
  const objs = G.nodes.filter(n=>n.kind==='object'&&n.rs!==null).length;
  document.getElementById('hud').innerHTML =
    `<b>Escape-reason set clusters</b><br>
     ${objs.toLocaleString()} objects · ${REASON_CLUSTERS.length} distinct reason sets ·
     ${cs.length-(other?1:0)} drawn individually${other?` · ${other.count.toLocaleString()} objects in "other" across ${other.distinctSets} sets`:``}
     <br><span style="color:#666">hover a square for its full set · click to list its members · drag to pan · wheel to zoom</span>`;
  fit({w:totalW, h:y});
}

function show(key) {
  if (typeof key === 'string' && key.startsWith('rs:')) {
    // drill-down: a cluster was clicked, so name the SET in full and list its members.
    // Naming the set is the point — the label under the square is clipped to the square's
    // width, so without this you cannot tell which of two similar sets you opened.
    const c = clustersToDraw()[+key.slice(3)];
    current = key;
    const rs = c.reasons || [];
    const box = document.getElementById('results');
    box.innerHTML = `<div class="row" data-back="1"><b>&#8592; back to all clusters</b></div>` +
      `<div class="setbox">
         <div class="seths">${c.reasons===null ? 'other — '+c.distinctSets+' further sets'
                              : (rs.length ? rs.length+' reason'+(rs.length===1?'':'s') : 'no reason')}
           · ${c.count.toLocaleString()} object${c.count===1?'':'s'}${HAS_SPLIT?' · '+c.inherited.toLocaleString()+' with an inherited reason':''}</div>
         ${c.reasons===null ? '<div class="m">an aggregate of every set outside the top N</div>'
           : (rs.length ? rs.map(r => `<div class="rsn${SURRENDER.has(r)?' surr':''}">${esc(r)}${SURRENDER.has(r)?' <em>'+notCauseLabel(r)+'</em>':''}</div>`).join("")
                        : '<div class="m">these objects do not escape</div>')}
       </div>` +
      c.members.slice(0,300).map(i => `<div class="row" data-m="${i}"><div>${esc(NODES[i].label)}</div>
        <div class="m">${esc(short(NODES[i].method))} · ${esc(NODES[i].escapeStatus||'unresolved')}${(NODES[i].inh&&NODES[i].inh.length)?' · inherited: '+esc(NODES[i].inh.join(', ')):''}</div></div>`).join("") +
      (c.members.length>300?`<div class="row"><em>${c.members.length-300} more not listed</em></div>`:"");
    box.querySelectorAll('.row[data-m]').forEach(r => r.onclick = () => {
      document.getElementById('mode').value='hops'; renderResults(); show(+r.dataset.m); });
    box.querySelector('.row[data-back]').onclick = () => { current=null; renderResults(); showClusters(); };
    document.getElementById('hud').innerHTML =
      `<b>${esc(setLabel(c))}</b><br>
       ${c.count.toLocaleString()} object${c.count===1?'':'s'} (${pct(c.count)} of ${RS_TOTAL.toLocaleString()}) ·
       ${c.reasons===null ? 'mixed reason counts' : rs.length+' reason'+(rs.length===1?'':'s')}
       ${c.hasSurrender?' · <b style="color:#b00">contains a surrender or unresolved-chain reason</b>':''}
       ${HAS_SPLIT?'<br>'+c.inherited.toLocaleString()+' of these carry an inherited reason ('+INH_NOTE+')':''}
       <br><span style="color:#666">members listed on the left · click one to open its neighbourhood</span>`;
    showClusters(true);
    return;
  }
  current = key;
  setLegend(document.getElementById('mode').value, 0);
  const sg = subgraph(key);
  const root = document.getElementById('mode').value === 'method' ? null : key;
  const L = layout(sg, root);
  const parts = [];
  parts.push(`<defs>${Object.entries(STYLE).map(([k,s]) =>
    `<marker id="a_${k}" markerWidth="9" markerHeight="9" refX="9" refY="3" orient="auto">
       <path d="M0,0 L0,6 L9,3 z" fill="${s.c}"/></marker>`).join("")}</defs>`);
  parts.push(`<g id="scene">`);
  // Parallel edges between the same pair used to be drawn on identical paths, so N edges
  // looked like one and their labels piled up on the same pixel. Give each its own slot.
  const slotOf = {}, slotSeen = {};
  sg.edges.forEach((e,i) => { const k=e.f+'>'+e.t; slotOf[i]=(slotSeen[k]||0); slotSeen[k]=slotOf[i]+1; });
  DRAWN_EDGES = sg.edges;
  sg.edges.forEach((e,ei) => {
    const a = L.pos[e.f], b = L.pos[e.t]; if (!a||!b) return;
    const s = STYLE[e.p] || STYLE.ARGUMENT;
    const k = slotOf[ei], off = (k % 2 ? 1 : -1) * Math.ceil(k/2) * 26;
    let d, lx, ly;
    if (e.f === e.t) {
      const x=a[0]+NW/2, y=a[1]+NH, w=70+k*24, h=52+k*20;
      d = `M ${x-16} ${y} C ${x-w} ${y+h}, ${x+w} ${y+h}, ${x+16} ${y}`; lx=x; ly=y+h*0.85;
    } else if (Math.abs(a[1]-b[1]) < 1) {
      const y=a[1]+NH/2, rt=b[0]>a[0];
      const x1=rt?a[0]+NW:a[0], x2=rt?b[0]:b[0]+NW, lift=(rt?-48:48)-(rt?1:-1)*k*22;
      d = `M ${x1} ${y} C ${x1+(rt?24:-24)} ${y+lift}, ${x2-(rt?24:-24)} ${y+lift}, ${x2} ${y}`;
      lx=(x1+x2)/2; ly=y+lift*0.7;
    } else {
      const x1=a[0]+NW/2, y1=a[1]+NH, x2=b[0]+NW/2, y2=b[1], my=(y1+y2)/2;
      d = `M ${x1} ${y1} C ${x1+off} ${my}, ${x2+off} ${my}, ${x2} ${y2}`;
      lx=(x1+x2)/2+off*0.75; ly=my;
    }
    // A transparent fat path under the visible one: a 2 px curve is essentially unclickable,
    // and pointer-events:stroke makes only the ribbon around the line hit, not its bounding box.
    parts.push(`<g class="ed" data-ei="${ei}" data-f="${e.f}" data-t="${e.t}" style="cursor:pointer">
      <path d="${d}" fill="none" stroke="transparent" stroke-width="14" style="pointer-events:stroke"/>
      <path class="wire" d="${d}" fill="none" stroke="${s.c}" stroke-width="${s.w}"
        ${s.d?`stroke-dasharray="${s.d}"`:""} marker-end="url(#a_${e.p})" style="pointer-events:none"/>
      ${e.lab?`<text x="${lx}" y="${ly-3}" font-size="10" text-anchor="middle" fill="#222" style="pointer-events:none">.${esc(e.lab)}</text>`:""}
    </g>`);
  });
  sg.nodes.forEach(n => {
    const p = L.pos[n.id]; if (!p) return;
    const fill = nodeFill(n);
    const stroke = n.libraryBoundary ? "#b00" : "#222";
    const sw = n.libraryBoundary ? 2 : 1.3;
    const dash = n.kind === 'object' ? "" : `stroke-dasharray="5,3"`;
    // The reason set on the node itself: as a hover tooltip always, and as the node's second
    // line when colour is carrying reason information, so the colour is never the only clue.
    const rsTxt = (n.rs === null ? "no .reasons data"
                : (n.rs.length ? n.rs.join(" + ") : "no reason — does not escape"))
                + ((n.inh && n.inh.length) ? "\\ninherited from its component: " + n.inh.join(" + ") : "");
    const cmode = colourBy();
    const sub = (cmode === 's') ? short(n.method)
              : (n.rs === null ? short(n.method)
                 : (n.rs.length ? n.rs.length + " reason" + (n.rs.length===1?"":"s") + ": "
                                  + clip(n.rs.join("+"), 30)
                                : "no reason"));
    parts.push(`<g class="nd" data-id="${encodeURIComponent(n.id)}" data-n="${n.id}" style="cursor:pointer">
      <title>${esc(n.label)}\n${esc(n.method||'')}\n${esc(n.escapeStatus||'unresolved')}\n${esc(rsTxt)}</title>
      <rect x="${p[0]}" y="${p[1]}" width="${NW}" height="${NH}" rx="8" fill="${fill}"
            stroke="${stroke}" stroke-width="${sw}" ${dash}/>
      <text x="${p[0]+NW/2}" y="${p[1]+18}" font-size="11" text-anchor="middle" fill="#111">${esc(clip(n.label,34))}</text>
      <text x="${p[0]+NW/2}" y="${p[1]+33}" font-size="9.5" text-anchor="middle" fill="#333">${esc(clip(sub,38))}</text>
    </g>`);
  });
  parts.push(`</g>`);
  cv.innerHTML = parts.join("");
  cv.querySelectorAll('.nd').forEach(g => g.onclick = ev => {
    ev.stopPropagation();
    if (ev.shiftKey) { pinNode(+g.dataset.n); return; }   // shift-click keeps the isolation up
    const id = decodeURIComponent(g.dataset.id);
    if (document.getElementById('mode').value === 'method') {
      const m = (NODES[id]||{}).method; if (m) show(m);
    } else show(id);
  });
  cv.querySelectorAll('.ed').forEach(g => {
    g.onclick = ev => { ev.stopPropagation(); pinEdge(+g.dataset.ei); };
    g.onmouseenter = () => { if (!PINNED) isolateEdge(+g.dataset.ei); };
    g.onmouseleave = () => { if (!PINNED) clearIsolate(); };
  });
  // Hovering a node isolates it and everything it touches. This is the answer to "do these
  // two objects share an edge" at densities where the drawing cannot be: XSLTSchema.build has
  // 225 objects and 195 edges, and no arrangement of that many long curves is readable. So
  // stop trying to make every edge legible at once and make ONE legible on demand.
  cv.querySelectorAll('.nd').forEach(g => {
    g.onmouseenter = () => { if (!PINNED) isolateNode(+g.dataset.n); };
    g.onmouseleave = () => { if (!PINNED) clearIsolate(); };
  });
  cv.addEventListener('click', ev => { if (!ev.target.closest('.ed,.nd')) unpin(); });
  const kinds = [...activeKinds()].join(", ");
  document.getElementById('hud').innerHTML =
    `<b>${esc(document.getElementById('mode').value === 'method' ? short(key) : (NODES[key]||{}).label || key)}</b><br>
     ${sg.nodes.length} nodes · ${sg.edges.length} edges drawn · kinds: ${esc(kinds)}
     ${sg.truncated ? '<br><b style="color:#b00">truncated at '+CAP+' nodes — narrow the view</b>' : ''}
     <br><span style="color:#666">click any node to re-centre · drag to pan · wheel to zoom</span>`;
  fit(L);
}
// The edges currently on screen, so a click can name the one it hit.
let DRAWN_EDGES = [], PINNED = false;

// ---- isolation ------------------------------------------------------------------
// Everything below exists because a 195-edge method is not readable as a picture. Rather than
// pretend otherwise, the drawing fades to near-nothing and brings back only what you point at.
function scene() { return cv.querySelector('#scene'); }
function clearIsolate() {
  const s = scene(); if (!s) return;
  s.classList.remove('iso');
  s.querySelectorAll('.hot').forEach(el => el.classList.remove('hot'));
}
function markHot(edgeIdxs, nodeIds) {
  const s = scene(); if (!s) return;
  clearIsolate();
  s.classList.add('iso');
  edgeIdxs.forEach(i => { const g=s.querySelector(`.ed[data-ei="${i}"]`); if (g) g.classList.add('hot'); });
  nodeIds.forEach(n => { const g=s.querySelector(`.nd[data-n="${n}"]`); if (g) g.classList.add('hot'); });
}
function isolateEdge(ei) {
  const e = DRAWN_EDGES[ei]; if (!e) return;
  markHot([ei], [e.f, e.t]);
}
// Everything whose escaping feeds nid's, by forward closure over the drawn edges.
//
// Direction matters and is easy to get backwards. Stava's resolver escapes sobj when a
// SUCCESSOR escapes -- resolve()'s scan is `for (nxt : graph.get(sobj)) if
// (isEscapingObject(nxt)) SetComponent(Escape)`. heapviz orients dependency edges the same
// way, src -> the callee parameter or returnValue it depends on. So the objects that make X
// escape are the ones reachable by following edges OUT of X, not into it.
function contributorsOf(nid) {
  const outAdj = {};
  DRAWN_EDGES.forEach((e,i) => (outAdj[e.f] ||= []).push([e.t, i]));
  const seenN = new Set([nid]), seenE = [], q = [nid];
  while (q.length) {
    const v = q.shift();
    (outAdj[v]||[]).forEach(([w,i]) => {
      seenE.push(i);
      if (!seenN.has(w)) { seenN.add(w); q.push(w); }
    });
  }
  return {nodes: seenN, edges: seenE};
}
function isolateNode(nid) {
  if (document.getElementById('trace') && document.getElementById('trace').checked) {
    const cl = contributorsOf(nid);
    markHot(cl.edges, [...cl.nodes]);
    const others = [...cl.nodes].filter(i => i !== nid);
    const esc_ = others.filter(i => (NODES[i]||{}).escapeStatus === 'Escape');
    const withR = others.filter(i => (NODES[i]||{}).rs && NODES[i].rs.length);
    document.getElementById('hud').innerHTML =
      `<b>${esc((NODES[nid]||{}).label||'?')}</b>
       <span style="color:#666">${esc((NODES[nid]||{}).escapeStatus||'')}</span>
       <div style="margin-top:5px"><b>${others.length}</b> object${others.length===1?'':'s'}
       reachable from it over the drawn edges — these are what its escaping rests on.
       ${esc_.length} of them escape; ${withR.length} carry a recorded reason.</div>
       <div style="margin-top:4px;color:#666">Following edges OUT, because the resolver escapes
       an object when a SUCCESSOR escapes. Confined to the subgraph on screen, so it is a lower
       bound: widen the view to widen the trace.</div>
       ${(NODES[nid]||{}).escapeStatus === 'Escape' && !esc_.length
         ? `<div style="margin-top:4px;color:#b00">Nothing reachable from here escapes, yet this
            object does. Its escape is its own recorded reasons, or inherited from its SCC —
            SetComponent escapes a whole component at once, and that is not a path you can
            trace along edges.</div>` : ''}
       <div style="margin-top:4px;color:#666">shift-click to keep this up</div>`;
    return;
  }
  const keep = [], nodes = new Set([nid]);
  DRAWN_EDGES.forEach((e,i) => {
    if (e.f === nid || e.t === nid) { keep.push(i); nodes.add(e.f); nodes.add(e.t); }
  });
  markHot(keep, [...nodes]);
  const n = NODES[nid] || {};
  const outs = DRAWN_EDGES.filter(e => e.f === nid), ins = DRAWN_EDGES.filter(e => e.t === nid);
  const line = (arr, dir) => arr.length
    ? arr.slice(0,10).map(e => `<div>${dir} <b>${esc(NODES[dir==='&#8594;'?e.t:e.f]?.label||'?')}</b>`
        + ` <span style="color:${(STYLE[e.p]||STYLE.ARGUMENT).c}">${esc(e.p)}</span>`
        + `${e.lab?` <code>.${esc(e.lab)}</code>`:''}</div>`).join('')
      + (arr.length>10?`<div style="color:#666">${arr.length-10} more…</div>`:'')
    : '<div style="color:#666">none</div>';
  document.getElementById('hud').innerHTML =
    `<b>${esc(n.label||'?')}</b> <span style="color:#666">${esc(short(n.method))}`
    + `${n.escapeStatus?' · '+esc(n.escapeStatus):''}</span>
     <div style="margin-top:5px"><u>out (${outs.length})</u>${line(outs,'&#8594;')}</div>
     <div style="margin-top:4px"><u>in (${ins.length})</u>${line(ins,'&#8592;')}</div>
     <div style="margin-top:5px;color:#666">shift-click to keep this up · click to re-centre</div>`;
}
function pinEdge(ei) { PINNED = true; isolateEdge(ei); describeEdge(ei); }
function pinNode(nid) { PINNED = true; isolateNode(nid); }
function unpin() { PINNED = false; clearIsolate(); }
function describeEdge(ei) {
  const e = DRAWN_EDGES[ei]; if (!e) return;
  const s = STYLE[e.p] || STYLE.ARGUMENT;
  const A = NODES[e.f] || {}, B = NODES[e.t] || {};
  const side = (n, role) => `<tr><td style="color:#666;padding-right:8px">${role}</td>
      <td><b>${esc(n.label||'?')}</b><br><span style="color:#666">${esc(n.method||'')}</span>
      ${n.escapeStatus?`<br><span style="color:#666">${esc(n.escapeStatus)}</span>`:''}</td></tr>`;
  document.getElementById('hud').innerHTML =
    `<b style="color:${s.c}">${esc(e.p)}</b> <span style="color:#666">· ${esc(s.fam)}</span>
     ${e.lab?` · field <code>.${esc(e.lab)}</code>`:''}
     <div style="margin:4px 0 6px">${EDGE_DOC[e.p]||''}</div>
     <table style="font-size:11px">${side(A,'from')}${side(B,'to')}</table>
     ${(e.p==='CONTAINMENT'||e.p==='FIELD_LOAD')
       ? `<div style="margin-top:5px;color:#666">Both solid kinds live in the same
          <code>Fields:</code> map; this one is labelled ${esc(e.p)} only because the target
          object's type is <code>${esc(String(B.label||'?').split('@')[0])}</code>.</div>` : ''}`;
}
function clip(s,n){ s=String(s); return s.length>n ? s.slice(0,n-1)+"…" : s; }
function short(m){ if(!m) return ""; const x=String(m).replace(/^<|>$/g,'');
  const i=x.indexOf(':'); if(i<0) return clip(x,40);
  const cls=x.slice(0,i).split('.').pop(); const sig=x.slice(i+1).trim();
  const nm=sig.split('(')[0].split(' ').pop(); return clip(cls+"."+nm,40); }

// How far in from the left the graph has to start to clear the HUD and the legend, both of
// which float over the canvas on the left. Measured live rather than hardcoded, because both
// panels change size with their content and with the mode.
// An <svg> sized only by `width:100%` inside a flex column reports a 0x0 client rect in some
// engines even while it paints correctly — measured here: #main and #cv both 0x0 while the
// overlays inside them had real coordinates. So take the left/top from the element (those are
// right) and fall back to the viewport for the extent.
function paneBox() {
  const b = cv.getBoundingClientRect();
  const vw = window.innerWidth || document.documentElement.clientWidth || 0;
  const vh = window.innerHeight || document.documentElement.clientHeight || 0;
  return {left: b.left, top: b.top,
          width:  b.width  || Math.max(0, vw - b.left),
          height: b.height || Math.max(0, vh - b.top)};
}
function leftGutter() {
  const r = paneBox();
  let g = 0;
  ['hud','legend'].forEach(id => {
    const el = document.getElementById(id);
    if (!el || !el.offsetWidth || getComputedStyle(el).display === 'none') return;
    g = Math.max(g, el.getBoundingClientRect().right - r.left);
  });
  // Never surrender more than half the pane — but only when the pane is measurable. Some
  // embedded viewers report 0 for innerWidth, clientWidth AND visualViewport while painting
  // normally; clamping against a 0 width there would silently collapse the gutter to nothing
  // and put the graph straight back under the panels.
  g += 18;
  return r.width > 0 ? Math.min(g, r.width * 0.5) : g;
}

let LAST_L = null;
function fit(L) {
  LAST_L = L;
  const r = paneBox();
  const gut = leftGutter();
  // Fit to WIDTH only. Fitting height as well is what made a tall graph microscopic:
  // XSLTSchema.build lays out as 33 rows, so height-fitting asked for a scale of 0.06 and
  // produced a postage stamp. A tall graph is meant to be panned down, not shrunk to fit.
  // Floored so it never goes below readable-with-effort; below that, isolate instead.
  let k = 1;
  if (r.width > 0) {
    const availW = Math.max(120, r.width - gut - 28); // 28 clears the zoom buttons on the right
    k = Math.min(1, availW / (L.w || 1));
    if (!(k > 0)) k = 1;
    k = Math.max(k, 0.35);
  }
  // If the pane cannot be measured, leave the scale at 1 rather than inventing one from a
  // zero width, and still apply the gutter so the graph clears the overlays.
  view = {k, x: gut, y: 28};
  apply();
}

// Re-fit whenever the canvas actually has a size. This is not only for window resizing: on
// first load show() runs before layout has settled, so getBoundingClientRect() is 0x0, the
// gutter measures 0 and the width fit falls through to its floor. Observing the canvas catches
// the 0 -> N transition and re-fits once it is real.
new ResizeObserver(() => { if (LAST_L && paneBox().width > 0) fit(LAST_L); }).observe(cv);
window.addEventListener('resize', () => { if (LAST_L) fit(LAST_L); });
function apply() {
  const s = cv.querySelector('#scene');
  if (s) s.setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.k})`);
}
let drag=null;
cv.addEventListener('mousedown', e => { drag={x:e.clientX-view.x, y:e.clientY-view.y}; cv.classList.add('drag'); });
window.addEventListener('mouseup', () => { drag=null; cv.classList.remove('drag'); });
window.addEventListener('mousemove', e => { if(!drag) return; view.x=e.clientX-drag.x; view.y=e.clientY-drag.y; apply(); });
cv.addEventListener('wheel', e => { e.preventDefault();
  const f = e.deltaY < 0 ? 1.12 : 1/1.12;
  const r = cv.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  view.x = mx - (mx-view.x)*f; view.y = my - (my-view.y)*f; view.k *= f; apply(); }, {passive:false});
document.getElementById('zin').onclick = () => { view.k*=1.2; apply(); };
document.getElementById('zout').onclick = () => { view.k/=1.2; apply(); };
document.getElementById('zfit').onclick = () => { if(current) show(current); };

document.getElementById('q').addEventListener('input', renderResults);
document.getElementById('mode').addEventListener('change', () => {
  renderResults();
  if (document.getElementById('mode').value === 'reasonset') showClusters();
  else if (current) show(current);
});
document.getElementById('top').addEventListener('change', () => {
  renderResults();
  if (document.getElementById('mode').value === 'reasonset') showClusters();
});
document.getElementById('cby').addEventListener('change', () => {
  setLegend(document.getElementById('mode').value, 0);
  if (current && !String(current).startsWith('rs:')) show(current);
});
document.getElementById('trace').addEventListener('change', () => { unpin(); });
document.getElementById('hops').addEventListener('change', () => { if(current) show(current); });
document.getElementById('follow').addEventListener('change', () => { if(current) show(current); });
["CONTAINMENT","FIELD_LOAD","ARGUMENT","RETURN"].forEach(k =>
  document.getElementById('e_'+k).addEventListener('change', () => { if(current) show(current); }));

// The reason-set view is only offered when the graph actually carries reason data. Showing an
// empty cluster map would look like "this program has no escape reasons" rather than "this run
// was made by an uninstrumented Stava", and those are not the same statement.
if (!HAS_REASONS) {
  const opt = document.querySelector('#mode option[value=reasonset]');
  if (opt) { opt.disabled = true; opt.textContent += " — no .reasons in this run"; }
}
setLegend('method', 0);
renderResults();
show(METHOD_LIST[0]);
</script>
"""


def intern_graph(g):
    """Turn graph-full.json into an index-based payload.

    graph-full.json stays human-readable and is the interface other tools read; this is a
    transport encoding for the browser only. Node ids become array indices, and every
    repeated string (method signature, escape status, provenance, field name) moves to a
    table.

    Escape-reason SETS are interned the same way and for the same reason: at avrora scale
    thousands of objects share a few dozen distinct sets, so the sets go in a table and each
    node carries an index. An index of -1 means the run had no .reasons file at all, which is
    deliberately distinguished from the empty set (an object with no reason).
    """
    methods, statuses, provs, labels, rsets = {}, {}, {}, {}, {}

    def idx(table, key):
        if key not in table:
            table[key] = len(table)
        return table[key]

    order = {n["id"]: i for i, n in enumerate(g["nodes"])}
    nodes = []
    for n in g["nodes"]:
        rs = n.get("escapeReasons")
        nodes.append([
            n["label"],
            idx(methods, n.get("method") or ""),
            0 if n["kind"] == "object" else 1,
            n["s"] if n.get("s") is not None else -1,
            idx(statuses, n["escapeStatus"]) if n.get("escapeStatus") else -1,
            1 if n.get("libraryBoundary") else 0,
            idx(rsets, tuple(rs)) if rs is not None else -1,
            # patch 0005: the subset that fired on the object itself; -1 = split not recorded
            idx(rsets, tuple(n["ownReasons"])) if n.get("ownReasons") is not None else -1,
        ])
    edges = []
    for e in g["edges"]:
        f, t = order.get(e["f"]), order.get(e["t"])
        if f is None or t is None:
            continue
        edges.append([f, t, idx(provs, e["p"]),
                      idx(labels, e["lab"]) if e.get("lab") else -1])

    def flat(table):
        out = [None] * len(table)
        for k, v in table.items():
            out[v] = k
        return out

    return {"meta": g["meta"], "methods": flat(methods), "statuses": flat(statuses),
            "provs": flat(provs), "labels": flat(labels),
            "reasonsets": [list(t) for t in flat(rsets)],
            "surrender": sorted(SURRENDER),
            "gap": sorted(REASONS_GAP),
            "nodes": nodes, "edges": edges}


def main(args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(args)

    with open(a.graph, encoding="utf-8") as fh:
        g = json.load(fh)

    data = json.dumps(intern_graph(g), separators=(",", ":"))
    html = PAGE.replace("__TITLE__", a.title).replace("__DATA__", data)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("%s  (%.1f MB)" % (a.out, os.path.getsize(a.out) / 1e6))


if __name__ == "__main__":
    main()
