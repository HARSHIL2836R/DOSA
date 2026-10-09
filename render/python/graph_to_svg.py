#!/usr/bin/env python3
"""
graph_to_svg.py — graph.json -> .dot and .svg

Static figures for the report (PTA-Task-List task 13: static figures and an interactive
explorer are different tools; this is the former and does not try to be the latter).

Graphviz is not installed on this host and cannot be (no sudo, no apt), so the .svg is laid
out by this script. The .dot is emitted alongside so the same graph can be rendered by
graphviz wherever it exists; the two are not guaranteed to be pixel-identical, and the .svg
is the artefact of record.

RULES, all from the task spec and none of them negotiable:

  * Colour carries EXACTLY ONE meaning: equi-escape set membership. Not escape verdict, not
    type, not method, not provenance. The set id is also printed inside the node, so the
    figure never depends on colour alone (greyscale printing, colour-blind readers).
  * Edge STYLE carries provenance. Legend on every figure.
  * Escape / NoEscape sinks are a distinct shape and are UNCOLOURED.
  * Node label is Class@method:bci. Never a bare integer id.
  * Layout matches how a person draws it: allocation sites at the top, sinks at the bottom,
    one rank per containment depth.
  * Every figure is captioned with the JDK build string, the filter, the equi-escape
    definition in use, and what the colours mean.

Palette is Okabe-Ito (colour-blind safe).
"""

import argparse
import json
import html

# Okabe-Ito, colour-blind safe. Set id is printed in-node too, so greyscale still reads.
PALETTE = ["#56B4E9", "#E69F00", "#009E73", "#CC79A7",
           "#0072B2", "#D55E00", "#F0E442", "#999999"]

EDGE_STYLE = {
    # provenance    -> (svg dash, width, colour, dot style, legend text)
    "CONTAINMENT": ("", 2.2, "#222222", "solid",
                    "CONTAINMENT — field store (a.f = b), from the PTG Fields: map"),
    # A load-derived points-to edge is NOT containment: `a = b.f` says b.f points at
    # something, not that it is owned by b. Drawn distinctly so a benchmark figure cannot
    # be read as showing more heap structure than the run actually contains.
    "FIELD_LOAD": ("1,4", 1.6, "#2f6f4f", "dotted",
                   "FIELD_LOAD — field read (a = b.f), a points-to edge, not containment"),
    "ARGUMENT": ("7,4", 1.5, "#444444", "dashed",
                 "ARGUMENT — receiver/argument of a call, from a [T] conditional value"),
    "RETURN": ("2,3", 1.5, "#444444", "dotted", "RETURN — escape by return"),
    "UNIFICATION": ("8,3,2,3", 1.5, "#444444", "dashdot",
                    "UNIFICATION — formal/actual field-chain matching"),
    "SINK": ("3,3", 1.1, "#8a8a8a", "dotted",
             "resolved verdict (not a dependency edge)"),
}

NODE_W, NODE_H = 196, 42
H_GAP, V_GAP = 34, 96
MARGIN_X, MARGIN_TOP = 40, 78


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def focus_subgraph(g, focus, hide_params=False):
    """Restrict to one method's objects plus everything they point at.

    hide_params drops callee-parameter nodes and the ARGUMENT edges into them. That loses
    real information, so it is only for the presentation figure; graph.json always keeps
    them and the full figure shows them.
    """
    if focus:
        keep = {n["id"] for n in g["nodes"]
                if n["kind"] != "sink" and n.get("method") == focus}
        edges = [e for e in g["edges"] if e["fromNode"] in keep]
        for e in edges:
            keep.add(e["toNode"])
        nodes = [n for n in g["nodes"] if n["id"] in keep]
    else:
        nodes, edges = list(g["nodes"]), list(g["edges"])

    if hide_params:
        drop = {n["id"] for n in nodes if n["kind"] == "param"}
        nodes = [n for n in nodes if n["id"] not in drop]
        edges = [e for e in edges
                 if e["fromNode"] not in drop and e["toNode"] not in drop]
    return nodes, edges


def rank_nodes(nodes, edges):
    """Containment depth. SCC members share a rank, so a cycle sits on one row."""
    ids = {n["id"] for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    # Rank by heap edges, which means containment AND field loads. A benchmark method often
    # has no stores at all, and ranking on containment alone would drop every node onto one
    # row and produce a figure metres wide.
    cont = [e for e in edges
            if e["provenance"] in ("CONTAINMENT", "FIELD_LOAD") and not e.get("derived")
            and e["fromNode"] in ids and e["toNode"] in ids]
    # a parameter that is the BASE of field reads (`this.f`) belongs at the top with the
    # allocations, not in the callee-parameter band at the bottom
    heap_sources = {e["fromNode"] for e in cont}

    # group by definition-C set where available, so a cycle is one rank
    def is_heap_node(n):
        return n["kind"] == "object" or n["id"] in heap_sources

    grp = {}
    for n in nodes:
        if n["kind"] == "object":
            grp[n["id"]] = ("scc", n.get("equiEscapeSetC"))
        else:
            grp[n["id"]] = ("solo", n["id"])

    gadj, gin = {}, {}
    for e in cont:
        a, b = grp[e["fromNode"]], grp[e["toNode"]]
        if a == b:
            continue
        gadj.setdefault(a, set()).add(b)
        gin[b] = gin.get(b, 0) + 1

    depth = {}
    order = sorted({grp[n["id"]] for n in nodes if is_heap_node(n)}, key=str)
    for gk in order:
        depth[gk] = 0
    changed = True
    guard = 0
    while changed and guard < 64:
        changed, guard = False, guard + 1
        for a, bs in gadj.items():
            for b in bs:
                if depth.get(b, 0) < depth.get(a, 0) + 1:
                    depth[b] = depth.get(a, 0) + 1
                    changed = True

    maxd = max(depth.values()) if depth else 0
    rank = {}
    for n in nodes:
        if is_heap_node(n):
            rank[n["id"]] = depth.get(grp[n["id"]], 0)
        elif n["kind"] == "sink":
            rank[n["id"]] = maxd + 2
        else:
            rank[n["id"]] = maxd + 1
    return rank


def layout(nodes, edges, max_per_row=6):
    rank = rank_nodes(nodes, edges)
    # compact away ranks left empty by --hide-params, so there is no blank band
    used = sorted({rank[n["id"]] for n in nodes})
    remap = {r: i for i, r in enumerate(used)}
    rank = {k: remap[v] for k, v in rank.items()}
    grouped = {}
    for n in nodes:
        grouped.setdefault(rank[n["id"]], []).append(n)
    for r in grouped:
        grouped[r].sort(key=lambda n: (n.get("bci") if n.get("bci") is not None else 9999,
                                       n["id"]))
    # Wrap wide ranks onto several visual rows. A benchmark method can put a dozen loaded
    # objects at the same depth, and one row of twelve is two metres of SVG nobody can read.
    rows, out_rank = {}, 0
    for r in sorted(grouped):
        chunk = grouped[r]
        for i in range(0, len(chunk), max_per_row):
            rows[out_rank] = chunk[i:i + max_per_row]
            out_rank += 1
    rank = {n["id"]: ri for ri, rn in rows.items() for n in rn}
    widest = max(len(v) for v in rows.values())
    total_w = widest * NODE_W + (widest - 1) * H_GAP
    pos = {}
    for r in sorted(rows):
        row = rows[r]
        row_w = len(row) * NODE_W + (len(row) - 1) * H_GAP
        x0 = MARGIN_X + (total_w - row_w) / 2
        for i, n in enumerate(row):
            pos[n["id"]] = (x0 + i * (NODE_W + H_GAP),
                            MARGIN_TOP + r * (NODE_H + V_GAP))
    return pos, rows, total_w


def esc(s):
    return html.escape(str(s), quote=True)


def wrap(text, width):
    """Wrap to a list of lines; the SVG has no flow layout so this is done by hand."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def node_fill(n, definition):
    if n["kind"] == "sink":
        return "#ffffff"
    if n["kind"] == "param":
        return "#f4f4f4"
    sid = n.get("equiEscapeSetS") if definition == "S" else n.get("equiEscapeSetC")
    if sid is None:
        return "#ffffff"
    return PALETTE[sid % len(PALETTE)]


def edge_path(p1, p2, slot=0):
    """slot separates parallel edges between the same pair, so their labels do not collide."""
    if p1 == p2:
        # self-loop: a condensation node whose set contains edges to itself
        x, y = p1[0] + NODE_W * 0.5, p1[1] + NODE_H
        w, h = 66 + slot * 26, 42 + slot * 22
        return ("M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f"
                % (x - 18, y, x - w, y + h, x + w, y + h, x + 18, y)), \
               (x, y + h * 0.82 + 4)
    return _edge_path_pair(p1, p2, slot)


def _edge_path_pair(p1, p2, slot=0):
    x1, y1 = p1[0] + NODE_W / 2, p1[1] + NODE_H
    x2, y2 = p2[0] + NODE_W / 2, p2[1]
    if abs(p1[1] - p2[1]) < 1:
        # Same rank - this is a cycle. The two arcs of a 2-cycle must go to OPPOSITE sides,
        # or they overlap into an unreadable bowtie: left-to-right arcs above, right-to-left
        # arcs below.
        y1 = p1[1] + NODE_H / 2
        y2 = p2[1] + NODE_H / 2
        rightward = p2[0] > p1[0]
        lift = (-54 - slot * 22) if rightward else (54 + slot * 22)
        x1 = p1[0] + NODE_W if rightward else p1[0]
        x2 = p2[0] if rightward else p2[0] + NODE_W
        bow = 26 if rightward else -26
        label_y = y1 + lift * 0.72 + (0 if rightward else 13)
        return "M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" % (
            x1, y1, x1 + bow, y1 + lift, x2 - bow, y2 + lift, x2, y2), \
               ((x1 + x2) / 2, label_y)
    my = (y1 + y2) / 2
    return "M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" % (
        x1, y1, x1, my, x2, my, x2, y2), ((x1 + x2) / 2, my)


def render_svg(g, nodes, edges, definition, caption_lines, out, max_per_row=6):
    pos, rows, total_w = layout(nodes, edges, max_per_row)
    by_id = {n["id"]: n for n in nodes}
    maxr = max(rows)
    # canvas must grow with the caption, or the disclaimer lines fall off the bottom
    height = (MARGIN_TOP + (maxr + 1) * (NODE_H + V_GAP)
              + 6 + 168 + max(0, len(caption_lines) - 2) * 15 + 26)
    width = max(total_w + 2 * MARGIN_X, 860)

    used_prov = sorted({e["provenance"] for e in edges})
    sets_used = sorted({(n.get("equiEscapeSetS") if definition == "S"
                         else n.get("equiEscapeSetC"))
                        for n in nodes if n["kind"] == "object"},
                       key=lambda v: (v is None, v))

    o = []
    o.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif">'
             % (width, height, width, height))
    o.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    o.append('<defs>')
    for name, col in (("ah", "#222222"), ("ahl", "#8a8a8a"), ("ahd", "#444444")):
        o.append('<marker id="%s" markerWidth="9" markerHeight="9" refX="8" refY="3" '
                 'orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="%s"/></marker>'
                 % (name, col))
    o.append('</defs>')

    # title
    o.append('<text x="%d" y="30" font-size="17" font-weight="bold" fill="#111">%s</text>'
             % (MARGIN_X, esc(caption_lines[0])))
    o.append('<text x="%d" y="52" font-size="12" fill="#555">%s</text>'
             % (MARGIN_X, esc(caption_lines[1])))

    # rank guides
    for r in sorted(rows):
        y = MARGIN_TOP + r * (NODE_H + V_GAP) + NODE_H / 2
        kinds = {n["kind"] for n in rows[r]}
        lbl = ("sinks" if kinds == {"sink"} else
               "callee parameters" if kinds == {"param"} else
               "allocation sites" if r == 0 else
               "containment depth %d" % r)
        o.append('<text x="6" y="%.1f" font-size="9" fill="#bbb">%s</text>'
                 % (y, esc(lbl)))

    # edges first, so nodes sit on top
    slot_of = {}
    for e in edges:
        k = (e["fromNode"], e["toNode"])
        slot_of[id(e)] = slot_of.get(k, 0)
        slot_of[k] = slot_of.get(k, 0) + 1
    for e in edges:
        if e.get("derived"):
            continue
        if e["fromNode"] not in pos or e["toNode"] not in pos:
            continue
        dash, w, col, _dot, _leg = EDGE_STYLE.get(e["provenance"], EDGE_STYLE["ARGUMENT"])
        d, mid = edge_path(pos[e["fromNode"]], pos[e["toNode"]], slot_of[id(e)])
        marker = "ahl" if e["provenance"] == "SINK" else (
            "ah" if e["provenance"] == "CONTAINMENT" else "ahd")
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f" %s '
                 'marker-end="url(#%s)"/>'
                 % (d, col, w, ('stroke-dasharray="%s"' % dash) if dash else "", marker))
        if e.get("fieldPath"):
            o.append('<text x="%.1f" y="%.1f" font-size="10" fill="#222" '
                     'text-anchor="middle">.%s</text>'
                     % (mid[0], mid[1] - 3, esc(".".join(e["fieldPath"]))))

    # nodes
    for n in nodes:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        fill = node_fill(n, definition)
        sid = n.get("equiEscapeSetS") if definition == "S" else n.get("equiEscapeSetC")
        if n["kind"] == "sink":
            k = 16
            o.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f '
                     '%.1f,%.1f %.1f,%.1f" fill="%s" stroke="#111" stroke-width="2.2"/>'
                     % (x + k, y, x + NODE_W - k, y, x + NODE_W, y + NODE_H / 2,
                        x + NODE_W - k, y + NODE_H, x + k, y + NODE_H, x, y + NODE_H / 2,
                        fill))
        elif n["kind"] == "param":
            o.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="3" fill="%s" '
                     'stroke="#777" stroke-width="1.2" stroke-dasharray="5,3"/>'
                     % (x, y, NODE_W, NODE_H, fill))
        else:
            o.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="8" fill="%s" '
                     'stroke="#222" stroke-width="1.4"/>' % (x, y, NODE_W, NODE_H, fill))

        label = n.get("label") or n["id"]
        fs = 11 if len(label) <= 26 else 9.5
        o.append('<text x="%.1f" y="%.1f" font-size="%.1f" text-anchor="middle" '
                 'fill="#111">%s</text>'
                 % (x + NODE_W / 2, y + NODE_H / 2 + (0 if n["kind"] == "sink" else -3),
                    fs, esc(label)))
        if n["kind"] == "object":
            o.append('<text x="%.1f" y="%.1f" font-size="9.5" text-anchor="middle" '
                     'fill="#333">set %s &#183; %s</text>'
                     % (x + NODE_W / 2, y + NODE_H - 8, esc(sid),
                        esc(n.get("escapeStatus") or "?")))

    # legend
    ly = MARGIN_TOP + (maxr + 1) * (NODE_H + V_GAP) + 6
    o.append('<rect x="%d" y="%.1f" width="%d" height="150" rx="6" fill="#fbfbfb" '
             'stroke="#ddd"/>' % (MARGIN_X, ly, width - 2 * MARGIN_X))
    o.append('<text x="%d" y="%.1f" font-size="12" font-weight="bold" fill="#111">'
             'Legend</text>' % (MARGIN_X + 12, ly + 20))

    yy = ly + 40
    o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">Colour = equi-escape set '
             '(definition %s). Nothing else is coloured. Set id is printed in each node, so '
             'the figure does not depend on colour.</text>'
             % (MARGIN_X + 12, yy, esc(definition)))
    yy += 16
    sx = MARGIN_X + 12
    for sid in sets_used:
        col = PALETTE[sid % len(PALETTE)] if sid is not None else "#ffffff"
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="3" fill="%s" '
                 'stroke="#222"/>' % (sx, yy - 11, col))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">set %s</text>'
                 % (sx + 19, yy, esc(sid)))
        sx += 74
    yy += 22
    for prov in used_prov:
        dash, w, col, _d, leg = EDGE_STYLE[prov]
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="%.1f" '
                 '%s marker-end="url(#ahd)"/>'
                 % (MARGIN_X + 12, yy - 4, MARGIN_X + 60, yy - 4, col, w,
                    ('stroke-dasharray="%s"' % dash) if dash else ""))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">%s</text>'
                 % (MARGIN_X + 70, yy, esc(leg)))
        yy += 15
    o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">Rounded box = abstract '
             'object &#183; dashed box = callee parameter &#183; hexagon = sink '
             '(uncoloured).</text>' % (MARGIN_X + 12, yy))

    # caption
    cy = ly + 168
    for line in caption_lines[2:]:
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#444">%s</text>'
                 % (MARGIN_X, cy, esc(line)))
        cy += 15

    o.append('</svg>')
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o) + "\n")


def render_dot(g, nodes, edges, definition, caption_lines, out):
    lines = ['digraph heap {', '  rankdir=TB;', '  graph [fontsize=10];',
             '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10];',
             '  edge [fontname="Helvetica" fontsize=9];',
             '  label=%s;' % json.dumps("\\n".join(caption_lines)), '  labelloc=b;']
    for n in nodes:
        sid = n.get("equiEscapeSetS") if definition == "S" else n.get("equiEscapeSetC")
        fill = node_fill(n, definition)
        if n["kind"] == "sink":
            shape, style = "hexagon", "filled"
        elif n["kind"] == "param":
            shape, style = "box", "filled,dashed"
        else:
            shape, style = "box", "rounded,filled"
        lbl = n.get("label") or n["id"]
        if n["kind"] == "object":
            lbl += "\\nset %s | %s" % (sid, n.get("escapeStatus"))
        lines.append('  %s [label=%s shape=%s style="%s" fillcolor="%s"];'
                     % (json.dumps(n["id"]), json.dumps(lbl), shape, style, fill))
    for e in edges:
        if e.get("derived"):
            continue
        _dash, _w, col, dot, _leg = EDGE_STYLE.get(e["provenance"], EDGE_STYLE["ARGUMENT"])
        attrs = ['style="%s"' % dot, 'color="%s"' % col]
        if e["provenance"] == "CONTAINMENT":
            attrs.append("penwidth=2")
        if e.get("fieldPath"):
            attrs.append('label=%s' % json.dumps("." + ".".join(e["fieldPath"])))
        lines.append('  %s -> %s [%s];' % (json.dumps(e["fromNode"]),
                                           json.dumps(e["toNode"]), " ".join(attrs)))
    lines.append('}')
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--definition", choices=["S", "C"], default="S")
    ap.add_argument("--focus", default=None, help="restrict to one method signature")
    ap.add_argument("--max-per-row", type=int, default=6,
                    help="wrap ranks wider than this onto extra rows")
    ap.add_argument("--hide-params", action="store_true",
                    help="drop callee-parameter nodes; presentation figure only")
    ap.add_argument("--title", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--dot", required=True)
    a = ap.parse_args()

    g = load(a.graph)
    nodes, edges = focus_subgraph(g, a.focus, a.hide_params)
    m = g["meta"]

    objs = [n for n in nodes if n["kind"] == "object"]
    ne = sum(1 for n in objs if n["escapeStatus"] == "NoEscape")
    es = sum(1 for n in objs if n["escapeStatus"] == "Escape")
    nsets = len({(n.get("equiEscapeSetS") if a.definition == "S"
                  else n.get("equiEscapeSetC")) for n in objs})

    caption = [
        a.title,
        (a.focus or "all application methods"),
        "JDK: %s   |   Stava config: %s" % (m["jdk"], m["config"]),
        "Filter: %s" % m["filter"],
        "Equi-escape definition %s = %s" % (
            a.definition, m["definitionS"] if a.definition == "S" else m["definitionC"]),
        "Colours mean equi-escape set membership and nothing else. "
        "%d objects, %d NoEscape, %d Escape, %d sets." % (len(objs), ne, es, nsets),
        "Edges from the pre-resolution half of the .info files; verdicts from the "
        "post-resolution half. Derived [F] conditional values are not drawn.",
    ]
    if m.get("view"):
        # the reconstruction disclaimer must appear on the figure, not only in the JSON
        caption += wrap(m["view"], 132)
    merged = (m.get("stitching") or {}).get("mergedNodes") or {}
    if merged:
        label_of = {n["id"]: n.get("label") or n["id"] for n in g["nodes"]}
        caption.append(
            "Merged by return-value aliasing: " + "; ".join(
                "%s stands for %d per-method nodes"
                % (label_of.get(k, k).replace(" (x%d)" % len(v), ""), len(v))
                for k, v in sorted(merged.items())))

    render_svg(g, nodes, edges, a.definition, caption, a.svg, a.max_per_row)
    render_dot(g, nodes, edges, a.definition, caption, a.dot)
    print("%s\n%s" % (a.svg, a.dot))
    print("  %d nodes drawn, %d edges drawn, %d sets under %s"
          % (len(nodes), len([e for e in edges if not e.get("derived")]), nsets,
             a.definition))


if __name__ == "__main__":
    main()
