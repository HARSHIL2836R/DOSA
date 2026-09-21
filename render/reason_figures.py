#!/usr/bin/env python3
"""
reason_figures.py — graph.json / graph-full.json -> the three escape-reason figures.

Companion to render/graph_to_svg.py, which draws the PTG. This draws distributions over the
per-object escape-reason sets that an instrumented Stava writes to <dirname>.reasons and that
extract/info_to_graph.py joins onto graph.json. Same conventions as graph_to_svg.py, and for
the same reasons:

  * Graphviz is not installed on this host and cannot be (no sudo, no apt), so the .svg is laid
    out by this script and is the ARTEFACT OF RECORD. A .dot is emitted alongside.
    Note honestly what that .dot is: a bar chart is not a graph, so the .dot is a graphviz
    record-table restatement of the same numbers, not a second layout of the same picture.
    Figure 1 is a real cluster map and its .dot is a node-per-cluster graph.
  * Every figure carries the JDK build string, the Stava configuration, the filter, and one
    sentence on what it cannot show. That rule exists because this project already shipped one
    misleading number (Stava-Codebase-Map 5.1).

THE THREE FIGURES

  1. reason-set clusters   one cluster per DISTINCT reason set, area proportional to member
                           count, ordered by reasonCount then size, top N individually and the
                           remainder in one aggregated cluster whose count is shown. Colour is
                           an ordered SEQUENTIAL scale on reasonCount; a hatch marks any
                           cluster whose set contains a surrender reason.
  2. multiplicity          the reasonCount histogram, over all reasons and over real reasons
                           only. The per-count difference is a REDISTRIBUTION, not a share
                           (Reason-Pipeline-Spec F-E9). When the two are identical at every
                           count the second series is not drawn, and the figure says so.
  3. single-reason         of the objects with exactly one reason, which reason. Ranked bar.
                           The actionability list.

NOT A KNOWN PROGRAM CAUSE
  Two kinds of constant are drawn with the red hatch, and every legend names both:
  surrender (NO_BCI_*, CALLER_ONLY_UNRESOLVABLE: Stava gave up) and unresolved chain
  (SUCCESSOR_*: roots mode could not follow a propagated reason to a cause, see
  extract/info_to_graph.resolve_roots). Neither is the program escaping for a known reason.

COLOUR, and this is a deliberate deviation worth stating
  graph_to_svg.py's rule is "colour means equi-escape set and nothing else". These figures do
  not draw equi-escape sets at all, so there is no set for colour to mean. Here colour means
  reasonCount (figure 1), the all/real distinction (figure 2), or real/surrender (figure 3),
  and each figure says so in its own legend. Nothing is coloured for decoration.

USAGE
  python3 render/reason_figures.py --graph build/out/E09-pye/graph.json \\
      --title "E09" --out-prefix render/figures/E09-pye-reason
"""

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extract"))
from info_to_graph import (SURRENDER, REASONS_GAP, REASONS_SURRENDER,  # noqa: E402
                           reason_set_clusters)

GAP_REASONS = set(REASONS_GAP)
NOT_A_CAUSE_TEXT = ("surrender (Stava gave up: %s) or unresolved chain (roots mode could "
                    "not follow a propagated reason to a cause: %s)"
                    % (", ".join(REASONS_SURRENDER), ", ".join(REASONS_GAP)))


def kind_of(r):
    return "unresolved" if r in GAP_REASONS else "surrender" if r in SURRENDER else "real"

# ColorBrewer Blues, a sequential ramp. Sequential because reasonCount is ordered; the
# categorical Okabe-Ito palette graph_to_svg.py uses would imply the counts are unordered
# labels. Dark end is dark enough to need light text, which is handled in fg_for.
SEQ = ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6",
       "#2171b5", "#08519c", "#08306b"]

# figure 2's pair, and figure 3's real/surrender split. Both from Okabe-Ito.
C_ALL = "#0072B2"
C_REAL = "#E69F00"
C_SURRENDER = "#D55E00"
C_REALBAR = "#009E73"

MARGIN_X, MARGIN_TOP = 40, 78


def esc(s):
    return html.escape(str(s), quote=True)


def wrap(text, width):
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


def chars_for(px, font_size):
    """Characters of Helvetica at font_size that fit in px, at an average advance of 0.52 em.

    Every legend and table line is wrapped to this. Unwrapped lines ran past the right edge of
    the SVG, where a browser silently clips them (found by the 2026-09-14 audit)."""
    return max(20, int(px / (font_size * 0.52)))


def text_block(o, x, y, lines, font_size=10.5, fill="#333", step=15):
    for line in lines:
        o.append('<text x="%d" y="%.1f" font-size="%s" fill="%s" xml:space="preserve">%s</text>'
                 % (x, y, font_size, fill, esc(line)))
        y += step
    return y


def hanging(head, body, width):
    """head + body wrapped to width chars, continuation lines indented under the body."""
    parts = wrap(body, max(10, width - len(head))) or [""]
    return [head + parts[0]] + [" " * len(head) + p for p in parts[1:]]


def seq_fill(k, kmax):
    if k is None:
        return "#ffffff"
    if kmax <= 0:
        return SEQ[0]
    i = int(round((len(SEQ) - 1) * (k / float(kmax))))
    return SEQ[max(0, min(len(SEQ) - 1, i))]


def fg_for(fill):
    """Readable text colour on a sequential fill. The dark end of Blues needs white."""
    return "#ffffff" if fill in SEQ[6:] else "#111111"


def svg_open(width, height):
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
         'font-family="Helvetica,Arial,sans-serif">' % (width, height, width, height),
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         '<defs>',
         '<pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" '
         'patternUnits="userSpaceOnUse">'
         '<line x1="0" y1="0" x2="0" y2="7" stroke="#b00" stroke-width="2.4"/></pattern>',
         # patch 0005: the share of objects carrying a reason inherited from their component
         '<pattern id="inherit" width="6" height="5" patternUnits="userSpaceOnUse">'
         '<rect width="6" height="5" fill="#ffffff" fill-opacity="0.55"/>'
         '<line x1="0" y1="1" x2="6" y2="1" stroke="#222" stroke-width="1.3"/></pattern>',
         '</defs>']
    return o


def split_known(objs):
    """True when every object records the own/inherited split (patch 0005)."""
    return bool(objs) and all(n.get("ownReasons") is not None for n in objs)


def is_inherited(n):
    return bool(n.get("inheritedReasons"))


INHERIT_TEXT = ("an object carrying at least one reason that fired on ANOTHER member of its "
                "resolver component, which Stava escapes as a whole (Reason-Pipeline-Spec X-A4). "
                "The reason holds for the verdict, but it is not a separate cause of this object")


def inherit_rect(o, x, y, w, h):
    if h > 0.5:
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="url(#inherit)" '
                 'stroke="none"/>' % (x, y, w, h))


def svg_title(o, caption_lines):
    o.append('<text x="%d" y="30" font-size="17" font-weight="bold" fill="#111">%s</text>'
             % (MARGIN_X, esc(caption_lines[0])))
    o.append('<text x="%d" y="52" font-size="12" fill="#555">%s</text>'
             % (MARGIN_X, esc(caption_lines[1])))


def svg_caption(o, caption_lines, y):
    for line in caption_lines[2:]:
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#444">%s</text>'
                 % (MARGIN_X, y, esc(line)))
        y += 15
    return y


def write_svg(path, parts):
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")


def dot_label(caption_lines):
    """A graphviz label from the caption block.

    json.dumps gives DOT-legal quoting. The join is a REAL newline, not the two characters
    backslash-n: json.dumps turns a real newline into the escape DOT reads as a line break,
    whereas passing backslash-n through json.dumps escapes the backslash and DOT then prints
    a literal "n". ensure_ascii=False keeps the em dash an em dash rather than \u2014,
    which graphviz does not decode.
    """
    return json.dumps("\n".join(caption_lines), ensure_ascii=False)


def caption_base(meta, title, subtitle, cannot_show):
    return [
        title,
        subtitle,
        "JDK: %s   |   Stava config: %s" % (meta.get("jdk", "?"), meta.get("config", "?")),
        "Filter: %s" % meta.get("filter", "?"),
    ] + wrap("Reasons: %s" % meta.get("reasons", "not recorded in the graph's meta (produced by "
                                                 "an extractor older than 2026-09-14)"), 132) \
      + wrap("What this figure cannot show: " + cannot_show, 132)


# ---------------------------------------------------------------------------
# figure 1 — reason-set clusters
# ---------------------------------------------------------------------------

def short_set(reasons):
    """A label that fits in a square. Full names go in the side table."""
    if reasons is None:
        return "other"
    if not reasons:
        return "no reason"
    return " + ".join(r.replace("_", " ").title().replace(" ", "") for r in reasons)


def not_a_cause_tag(reasons):
    rs = set(reasons or ())
    tags = [t for t, hit in (("surrender", rs & (SURRENDER - GAP_REASONS)),
                             ("unresolved chain", rs & GAP_REASONS)) if hit]
    return "   [contains %s]" % " and ".join(tags) if tags else ""


def figure1(objs, meta, title, top, svg_path, dot_path):
    clusters, other = reason_set_clusters(objs, top)
    drawn = list(clusters) + ([other] if other else [])
    total = len(objs)
    if not drawn:
        print("figure 1: nothing to draw (no objects)", file=sys.stderr)
        return
    kmax = max([c["reasonCount"] for c in clusters] or [0])

    # side ∝ sqrt(count) so AREA is proportional to member count, which is what the figure
    # claims. A square per cluster rather than a squarified treemap: the treemap's aspect
    # ratios are what make its areas hard to compare, and comparing areas is the whole job.
    maxc = max(c["count"] for c in drawn)
    SIDE_MAX, SIDE_MIN = 132.0, 26.0

    def side(c):
        return SIDE_MIN + (SIDE_MAX - SIDE_MIN) * ((c / float(maxc)) ** 0.5)

    ROW_W = 980
    rows, cur, curw = [], [], 0.0
    for c in drawn:
        s = side(c["count"])
        if cur and curw + s + 14 > ROW_W:
            rows.append(cur)
            cur, curw = [], 0.0
        cur.append((c, s))
        curw += s + 14
    if cur:
        rows.append(cur)

    row_h = [max(s for _c, s in r) + 30 for r in rows]
    body_h = sum(row_h)
    LW = chars_for(ROW_W - 24, 10.5)
    leg_pre = (wrap("One square = one distinct escape-reason SET. Square AREA is proportional "
                    "to the number of objects with exactly that set. The big number is the set "
                    "size; the small number is the member count.", LW)
               + wrap("Colour = number of reasons, on an ordered sequential scale (light = few, "
                      "dark = many). It is the only thing colour means in this figure.", LW))
    split = split_known(objs)
    leg_post = (wrap("Red hatch (last swatch) = the set contains a reason that is not a known "
                     "program cause: a surrender or an unresolved chain, named in the caption.",
                     LW)
                + (wrap("Horizontal stripes = the share of the set's objects that carry an "
                        "INHERITED reason; the striped height is that share of the square. "
                        "Inherited means " + INHERIT_TEXT + ".", LW) if split else
                   wrap("No stripes: this run does not record which reasons are inherited from "
                        "the resolver component (it predates patch 0005).", LW))
                + wrap('Grey square = the aggregated "other" cluster. Its member count is shown; '
                       'it is never dropped.', LW))
    legend_h = 30 + 15 * len(leg_pre) + 30 + 15 * len(leg_post)
    TW = chars_for(ROW_W, 10)

    def inh_txt(c):
        return ("%6d inherited  " % c["inheritedCount"]) if split else ""

    table_lines = []
    for c in clusters:
        names = ", ".join(c["reasons"]) if c["reasons"] else "(none - does not escape)"
        table_lines += hanging("%2d reasons  %6d objects  %s" % (c["reasonCount"], c["count"],
                                                                 inh_txt(c)),
                               names + not_a_cause_tag(c["reasons"]), TW)
    if other:
        table_lines += hanging(" other      %6d objects  %s" % (other["count"], inh_txt(other)),
                               "across %d further distinct sets%s"
                               % (other["distinctSets"],
                                  "   [contains surrender or unresolved chain]"
                                  if other["hasSurrender"] else ""), TW)
    table_h = 26 + len(table_lines) * 15
    n_inh = sum(1 for n in objs if is_inherited(n)) if split else None
    cannot = ("how many objects each reason would account for on its own - a cluster is an "
              "exact SET, so an object with three reasons is in exactly one cluster and is "
              "counted once, not three times. Figure 3 is the per-reason view. "
              + ("%d of %d objects carry an inherited reason (the striped share, exact since "
                 "patch 0005); a set's reason COUNT still includes those reasons, so a large "
                 "striped square at a high count is mostly one component's union. "
                 % (n_inh, total) if split else
                 "A large cluster at a high reason count is usually one dependency-graph SCC, "
                 "whose members all carry the union of what fired anywhere in it; this run "
                 "cannot say which members. ")
              + "Hatched sets contain a " + NOT_A_CAUSE_TEXT + ".")
    cap = caption_base(meta, title, "%d objects, %d distinct reason sets, top %d drawn"
                       % (total, len(set(tuple(n.get("escapeReasons") or []) for n in objs)),
                          top), cannot)
    width = ROW_W + 2 * MARGIN_X
    height = int(MARGIN_TOP + body_h + 18 + legend_h + 12 + table_h + 12
                 + (len(cap) - 2) * 15 + 30)

    o = svg_open(width, height)
    svg_title(o, cap)

    y = MARGIN_TOP
    for r, rh in zip(rows, row_h):
        x = MARGIN_X
        for c, s in r:
            fill = seq_fill(c["reasonCount"], kmax) if c["reasons"] is not None else "#e8e8e8"
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s" '
                     'stroke="#222" stroke-width="1.2"/>' % (x, y, s, s, fill))
            if c["hasSurrender"]:
                o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" '
                         'fill="url(#hatch)" stroke="#b00" stroke-width="2.2"/>'
                         % (x, y, s, s))
            if split and c["count"]:
                # stripes over the TOP share of the square equal to the inherited share
                inherit_rect(o, x + 1, y + 1, s - 2, (s - 2) * c["inheritedCount"] / c["count"])
            fg = fg_for(fill)
            o.append('<text x="%.1f" y="%.1f" font-size="13" font-weight="bold" '
                     'text-anchor="middle" fill="%s">%s</text>'
                     % (x + s / 2, y + s / 2 - 2, fg,
                        esc("mix" if c["reasonCount"] is None else c["reasonCount"])))
            o.append('<text x="%.1f" y="%.1f" font-size="10.5" text-anchor="middle" '
                     'fill="%s">%s</text>'
                     % (x + s / 2, y + s / 2 + 13, fg, esc("%d" % c["count"])))
            if split and c["inheritedCount"] and s >= 60:
                o.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle" '
                         'fill="%s">%s</text>'
                         % (x + s / 2, y + s / 2 + 25, fg,
                            esc("%d inh." % c["inheritedCount"])))
            # Only label a square wide enough to hold a legible label. Below that the
            # labels of adjacent small squares overlap into an unreadable smear, and every
            # set is listed in full in the table below the legend anyway.
            lbl = short_set(c["reasons"])
            fit = max(0, int(s / 5.4))
            if fit >= 8:
                o.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle" '
                         'fill="#444">%s</text>'
                         % (x + s / 2, y + s + 12,
                            esc(lbl if len(lbl) <= fit else lbl[:fit - 1] + "…")))
            x += s + 14
        y += rh

    ly = y + 18
    o.append('<rect x="%d" y="%.1f" width="%d" height="%d" rx="6" fill="#fbfbfb" '
             'stroke="#ddd"/>' % (MARGIN_X, ly, width - 2 * MARGIN_X, legend_h))
    o.append('<text x="%d" y="%.1f" font-size="12" font-weight="bold" fill="#111">Legend'
             '</text>' % (MARGIN_X + 12, ly + 20))
    cy = text_block(o, MARGIN_X + 12, ly + 38, leg_pre)
    sx, sy = MARGIN_X + 12, cy - 7
    for k in range(0, kmax + 1):
        f = seq_fill(k, kmax)
        o.append('<rect x="%d" y="%.1f" width="16" height="14" rx="3" fill="%s" '
                 'stroke="#222"/>' % (sx, sy, f))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">%d</text>'
                 % (sx + 21, sy + 11, k))
        sx += 46
    o.append('<rect x="%d" y="%.1f" width="16" height="14" rx="3" fill="#e8e8e8" '
             'stroke="#b00" stroke-width="2.2"/>' % (sx + 16, sy))
    o.append('<rect x="%d" y="%.1f" width="16" height="14" rx="3" fill="url(#hatch)" '
             'stroke="#b00" stroke-width="2.2"/>' % (sx + 16, sy))
    if split:
        o.append('<rect x="%d" y="%.1f" width="16" height="14" rx="3" fill="#9ecae1" '
                 'stroke="#222"/>' % (sx + 46, sy))
        o.append('<rect x="%d" y="%.1f" width="16" height="14" rx="3" fill="url(#inherit)" '
                 'stroke="#222"/>' % (sx + 46, sy))
    text_block(o, MARGIN_X + 12, sy + 30, leg_post)

    ty = ly + legend_h + 24
    o.append('<text x="%d" y="%.1f" font-size="11" font-weight="bold" fill="#111">'
             'Reason sets, in draw order</text>' % (MARGIN_X, ty))
    ty = text_block(o, MARGIN_X, ty + 16, table_lines, font_size=10)

    svg_caption(o, cap, ty + 14)
    write_svg(svg_path, o)

    lines = ['digraph reasonsets {', '  rankdir=LR;', '  node [shape=box '
             'style="rounded,filled" fontname="Helvetica" fontsize=10];',
             '  label=%s;' % dot_label(cap), '  labelloc=b;']
    for i, c in enumerate(drawn):
        names = "other (%d sets)" % c.get("distinctSets", 0) if c["reasons"] is None \
            else (", ".join(c["reasons"]) or "(none)")
        fill = seq_fill(c["reasonCount"], kmax) if c["reasons"] is not None else "#e8e8e8"
        lbl = "%s\n%s reasons | %d objects" % (
            names, "mixed" if c["reasonCount"] is None else c["reasonCount"], c["count"])
        if split:
            lbl += " | %d inherited" % c["inheritedCount"]
        attrs = ['label=%s' % json.dumps(lbl), 'fillcolor="%s"' % fill]
        if c["hasSurrender"]:
            attrs += ['color="#b00"', 'penwidth=2.4']
        lines.append('  c%d [%s];' % (i, " ".join(attrs)))
    lines.append("}")
    with open(dot_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("%s\n%s" % (svg_path, dot_path))
    print("  %d clusters drawn, %d objects, %d in 'other'"
          % (len(drawn), total, other["count"] if other else 0))


# ---------------------------------------------------------------------------
# figure 2 — the multiplicity histogram, all reasons vs real reasons
# ---------------------------------------------------------------------------

def figure2(objs, meta, title, svg_path, dot_path):
    allc, realc = {}, {}
    alli, reali = {}, {}          # objects in each bucket carrying an inherited reason
    split = split_known(objs)
    for n in objs:
        ka, kr = n.get("reasonCount") or 0, n.get("realReasonCount") or 0
        allc[ka] = allc.get(ka, 0) + 1
        realc[kr] = realc.get(kr, 0) + 1
        if split and is_inherited(n):
            alli[ka] = alli.get(ka, 0) + 1
            reali[kr] = reali.get(kr, 0) + 1
    ks = sorted(set(allc) | set(realc))
    if not ks:
        print("figure 2: nothing to draw", file=sys.stderr)
        return
    peak = max(max(allc.values()), max(realc.values()))
    # Two identical series say nothing twice. Draw the second only when it differs somewhere.
    same = all(allc.get(k, 0) == realc.get(k, 0) for k in ks)

    BW, GAP, GRP = 44, 8, 42
    PLOT_H = 300
    PAIR = BW if same else 2 * BW + GAP
    width = max(860, 2 * MARGIN_X + len(ks) * (PAIR + GRP) + 60)
    n_surr = sum(1 for n in objs if (n.get("surrenderReasonCount") or 0) > 0)
    n_inh = sum(alli.values())
    cannot = ("which reasons those are. " +
              ("The striped share of each bar counts objects carrying an inherited reason (%d of "
               "%d objects, exact since patch 0005); their COUNT still includes the inherited "
               "reasons, so a tall striped bar at a high count is mostly one component reported "
               "once per member." % (n_inh, len(objs)) if split else
               "Nor whether a high count belongs to the object or to its dependency component: a "
               "resolver reason is stamped on every member of the SCC it fired in, so a tall bar "
               "at a high count can be one large component reported once per member, and this "
               "run cannot say which members."))
    cap = caption_base(meta, title,
                       ("%d objects; one bar per count: every object's reasons are all real, so "
                        "the all-reasons and real-reasons histograms are identical" % len(objs))
                       if same else
                       ("%d objects; left bar counts all reasons, right bar counts real reasons "
                        "only" % len(objs)), cannot)
    LW = chars_for(width - 2 * MARGIN_X - 24, 10.5)
    leg_count = wrap("%d of %d objects carry at least one reason that is not a known program "
                     "cause (surrender or unresolved chain). That count is the number worth "
                     "quoting." % (n_surr, len(objs)), LW)
    leg_notes = ([] if same else
                 wrap("The red number under each pair is all − real at that count. It is a "
                      "REDISTRIBUTION, not a share: an object with one real and one surrender "
                      "reason leaves bucket 2 and joins bucket 1, so the same object shows as +1 "
                      "here and −1 there.", LW))
    if split:
        leg_notes += wrap("Horizontal stripes (top of a bar) = the objects in that bar carrying "
                          "an INHERITED reason, %d of %d in all; the rest of the bar is objects "
                          "whose every reason fired on the object itself. Inherited means %s."
                          % (n_inh, len(objs), INHERIT_TEXT), LW)
    leg_notes += wrap("Percentages are of all %d objects in the population, bucket 0 included, "
                      "so each series sums to 100%%. Not a known cause: %s."
                      % (len(objs), NOT_A_CAUSE_TEXT), LW)
    legend_h = 30 + 15 * (len(leg_count) + len(leg_notes)) + 14
    height = int(MARGIN_TOP + PLOT_H + 60 + legend_h + 12 + (len(cap) - 2) * 15 + 30)

    o = svg_open(width, height)
    svg_title(o, cap)
    base_y = MARGIN_TOP + PLOT_H

    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = base_y - PLOT_H * f
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eee" '
                 'stroke-width="1"/>' % (MARGIN_X, gy, width - MARGIN_X, gy))
        o.append('<text x="%d" y="%.1f" font-size="9" fill="#aaa" text-anchor="end">%d</text>'
                 % (MARGIN_X - 6, gy + 3, int(round(peak * f))))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#333" stroke-width="1.4"/>'
             % (MARGIN_X, base_y, width - MARGIN_X, base_y))

    # denominator for the percentages: the whole population the figure is drawn over,
    # bucket 0 included. Both series share it, so the two columns of a pair are comparable.
    total = len(objs) or 1
    x = MARGIN_X + 24
    for k in ks:
        a, r = allc.get(k, 0), realc.get(k, 0)
        for val, inh, col, off in (((a, alli.get(k, 0), C_ALL, 0),) if same
                                   else ((a, alli.get(k, 0), C_ALL, 0),
                                         (r, reali.get(k, 0), C_REAL, BW + GAP))):
            h = PLOT_H * (val / float(peak)) if peak else 0
            o.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" fill="%s" '
                     'stroke="#222" stroke-width="0.8"/>'
                     % (x + off, base_y - h, BW, h, col))
            if split and val:
                inherit_rect(o, x + off + 0.5, base_y - h + 0.5, BW - 1, (h - 1) * inh / val)
            o.append('<text x="%.1f" y="%.1f" font-size="10" text-anchor="middle" '
                     'fill="#111">%d</text>' % (x + off + BW / 2, base_y - h - 5, val))
            # The share goes INSIDE the bar when there is room, so a tall bar never pushes
            # a second label line off the top of the plot; otherwise it sits above the count.
            pct = 100.0 * val / total
            if h >= 26:
                o.append('<text x="%.1f" y="%.1f" font-size="9.5" text-anchor="middle" '
                         'fill="#fff">%.1f%%</text>'
                         % (x + off + BW / 2, base_y - h + 14, pct))
            else:
                o.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle" '
                         'fill="#777">%.1f%%</text>'
                         % (x + off + BW / 2, base_y - h - 15, pct))
        gap = a - r
        if gap:
            o.append('<text x="%.1f" y="%.1f" font-size="9.5" text-anchor="middle" '
                     'fill="#b00">%+d</text>' % (x + PAIR / 2.0, base_y + 32, gap))
        o.append('<text x="%.1f" y="%.1f" font-size="11.5" text-anchor="middle" '
                 'fill="#111">%d</text>' % (x + PAIR / 2.0, base_y + 17, k))
        x += PAIR + GRP
    o.append('<text x="%.1f" y="%.1f" font-size="10.5" text-anchor="middle" fill="#555">'
             'number of escape reasons on one object</text>'
             % (width / 2.0, base_y + 52))

    ly = base_y + 60
    o.append('<rect x="%d" y="%.1f" width="%d" height="%d" rx="6" fill="#fbfbfb" '
             'stroke="#ddd"/>' % (MARGIN_X, ly, width - 2 * MARGIN_X, legend_h))
    o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#222"/>'
             % (MARGIN_X + 12, ly + 12, C_ALL))
    o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">all reasons</text>'
             % (MARGIN_X + 32, ly + 23))
    if not same:
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#222"/>'
                 % (MARGIN_X + 132, ly + 12, C_REAL))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">real reasons only '
                 '(surrender and unresolved-chain constants removed)</text>'
                 % (MARGIN_X + 152, ly + 23))
    if split:
        sx2 = MARGIN_X + (560 if not same else 132)
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#222"/>'
                 % (sx2, ly + 12, C_ALL))
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="url(#inherit)" '
                 'stroke="#222"/>' % (sx2, ly + 12))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">carries an inherited '
                 'reason</text>' % (sx2 + 20, ly + 23))
    cy = text_block(o, MARGIN_X + 12, ly + 44, leg_count, fill="#b00")
    text_block(o, MARGIN_X + 12, cy, leg_notes, fill="#555")

    svg_caption(o, cap, ly + legend_h + 24)
    write_svg(svg_path, o)

    # the first six columns keep their pre-0005 meaning and order (tools/viz_audit.py reads them)
    rows = "".join(
        '<TR><TD>%d</TD><TD>%d</TD><TD>%.1f%%</TD><TD>%d</TD><TD>%.1f%%</TD><TD>%+d</TD>%s</TR>'
        % (k, allc.get(k, 0), 100.0 * allc.get(k, 0) / total,
           realc.get(k, 0), 100.0 * realc.get(k, 0) / total,
           allc.get(k, 0) - realc.get(k, 0),
           ("<TD>%d</TD><TD>%d</TD>" % (alli.get(k, 0), reali.get(k, 0))) if split else "")
        for k in ks)
    dot = ['digraph multiplicity {', '  node [shape=plaintext fontname="Helvetica"];',
           '  label=%s;' % dot_label(cap), '  labelloc=b;',
           '  hist [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
           '<TR><TD>reasons</TD><TD>all</TD><TD>all %</TD><TD>real</TD><TD>real %</TD>'
           '<TD>gap</TD>'
           + ("<TD>all, inherited</TD><TD>real, inherited</TD>" if split else "")
           + '</TR>' + rows + '</TABLE>>];', '}']
    with open(dot_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(dot) + "\n")
    print("%s\n%s" % (svg_path, dot_path))
    print("  n     : %d objects" % total)
    print("  all  : %s" % ", ".join("%d:%d (%.1f%%)"
                                    % (k, allc.get(k, 0), 100.0 * allc.get(k, 0) / total)
                                    for k in ks))
    print("  real : %s" % ", ".join("%d:%d (%.1f%%)"
                                    % (k, realc.get(k, 0), 100.0 * realc.get(k, 0) / total)
                                    for k in ks))


# ---------------------------------------------------------------------------
# figure 3 — single-reason attribution
# ---------------------------------------------------------------------------

def figure3(objs, meta, title, svg_path, dot_path):
    single, single_inh = {}, {}
    split = split_known(objs)
    for n in objs:
        rs = n.get("escapeReasons") or []
        if len(rs) == 1:
            single[rs[0]] = single.get(rs[0], 0) + 1
            if split and is_inherited(n):
                single_inh[rs[0]] = single_inh.get(rs[0], 0) + 1
    ranked = sorted(single.items(), key=lambda kv: (-kv[1], kv[0]))
    n_single = sum(single.values())
    n_esc = sum(1 for n in objs if (n.get("escapeReasons") or []))
    if not ranked:
        print("figure 3: no single-reason objects", file=sys.stderr)
        ranked = []

    LBL_W, BAR_MAX, RH = 300, 460, 26
    # the value label after a full-width bar reads "N (p%)   own N, inherited N" when split
    width = max(860, 2 * MARGIN_X + LBL_W + BAR_MAX + (330 if split else 120))
    body_h = max(RH, len(ranked) * RH)
    peak = max([c for _r, c in ranked] or [1])
    n_single_inh = sum(single_inh.values())
    cannot = ("anything about objects with more than one reason. %d of the %d objects that "
              "escape at all have exactly one reason; the other %d are not in this figure, "
              "and a fix aimed at the top bar does not touch them."
              % (n_single, n_esc, n_esc - n_single)
              + (" Of the %d, %d carry their one reason by inheritance from their resolver "
                 "component (striped): fixing it on the object itself is not possible, because it "
                 "fired on another member." % (n_single, n_single_inh) if split else
                 " This run does not record whether an object's one reason fired on it or was "
                 "stamped on it by its resolver component."))
    cap = caption_base(meta, title,
                       "%d objects with exactly one escape reason, of %d that escape at all"
                       % (n_single, n_esc), cannot)
    legend_h = 76 if split else 56
    height = int(MARGIN_TOP + body_h + 26 + legend_h + 12 + (len(cap) - 2) * 15 + 30)

    o = svg_open(width, height)
    svg_title(o, cap)

    y = MARGIN_TOP
    for r, c in ranked:
        surr = r in SURRENDER
        w = BAR_MAX * (c / float(peak))
        o.append('<text x="%d" y="%.1f" font-size="10.5" text-anchor="end" fill="#111">%s'
                 '</text>' % (MARGIN_X + LBL_W - 10, y + 15, esc(r)))
        o.append('<rect x="%d" y="%.1f" width="%.1f" height="16" rx="2" fill="%s" '
                 'stroke="#222" stroke-width="0.8"/>'
                 % (MARGIN_X + LBL_W, y + 3, max(w, 1.0),
                    C_SURRENDER if surr else C_REALBAR))
        if surr:
            o.append('<rect x="%d" y="%.1f" width="%.1f" height="16" rx="2" '
                     'fill="url(#hatch)" stroke="#b00" stroke-width="1.6"/>'
                     % (MARGIN_X + LBL_W, y + 3, max(w, 1.0)))
        inh = single_inh.get(r, 0)
        if split and c:
            # stripes over the RIGHT share of the bar equal to the inherited share
            wi = max(w, 1.0) * inh / c
            inherit_rect(o, MARGIN_X + LBL_W + max(w, 1.0) - wi, y + 3.5, wi, 15)
        o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="#111">%s</text>'
                 % (MARGIN_X + LBL_W + max(w, 1.0) + 8, y + 15, esc(
                     "%d  (%.1f%%)%s" % (c, 100.0 * c / n_single if n_single else 0.0,
                                         ("   own %d, inherited %d" % (c - inh, inh))
                                         if split else ""))))
        y += RH

    ly = y + 26
    o.append('<rect x="%d" y="%.1f" width="%d" height="%d" rx="6" fill="#fbfbfb" '
             'stroke="#ddd"/>' % (MARGIN_X, ly, width - 2 * MARGIN_X, legend_h))
    o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#222"/>'
             % (MARGIN_X + 12, ly + 10, C_REALBAR))
    o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">real escape - a fix here is '
             'a change to the program</text>' % (MARGIN_X + 32, ly + 21))
    o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#b00" '
             'stroke-width="1.6"/>' % (MARGIN_X + 12, ly + 30, C_SURRENDER))
    o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="url(#hatch)" '
             'stroke="#b00" stroke-width="1.6"/>' % (MARGIN_X + 12, ly + 30))
    o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">surrender or unresolved chain '
             '- not a known program cause; a fix here is a change to Stava or to the '
             'instrumentation</text>' % (MARGIN_X + 32, ly + 41))
    if split:
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="%s" stroke="#222"/>'
                 % (MARGIN_X + 12, ly + 50, C_REALBAR))
        o.append('<rect x="%d" y="%.1f" width="14" height="14" rx="2" fill="url(#inherit)" '
                 'stroke="#222"/>' % (MARGIN_X + 12, ly + 50))
        o.append('<text x="%d" y="%.1f" font-size="10.5" fill="#333">striped share - the reason '
                 'is inherited from the resolver component: it fired on another member</text>'
                 % (MARGIN_X + 32, ly + 61))

    svg_caption(o, cap, ly + legend_h + 24)
    write_svg(svg_path, o)

    # the first three columns keep their pre-0005 meaning and order (tools/viz_audit.py)
    rows = "".join('<TR><TD>%s</TD><TD>%d</TD><TD>%s</TD>%s</TR>'
                   % (r, c, kind_of(r),
                      ("<TD>%d</TD><TD>%d</TD>" % (c - single_inh.get(r, 0), single_inh.get(r, 0)))
                      if split else "")
                   for r, c in ranked)
    dot = ['digraph single_reason {', '  node [shape=plaintext fontname="Helvetica"];',
           '  label=%s;' % dot_label(cap), '  labelloc=b;',
           '  ranked [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
           '<TR><TD>reason</TD><TD>objects</TD><TD>kind</TD>%s</TR>'
           % ("<TD>own</TD><TD>inherited</TD>" if split else "") + rows + '</TABLE>>];',
           '}']
    with open(dot_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(dot) + "\n")
    print("%s\n%s" % (svg_path, dot_path))
    for r, c in ranked:
        print("  %-30s %6d" % (r, c))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True,
                    help="graph.json or graph-full.json carrying escapeReasons on its nodes")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out-prefix", required=True,
                    help="figures are written to <prefix>-{clusters,multiplicity,single}"
                         ".{svg,dot}")
    ap.add_argument("--top-reason-sets", type=int, default=20)
    ap.add_argument("--only", choices=["1", "2", "3"], default=None)
    a = ap.parse_args()

    with open(a.graph, encoding="utf-8") as fh:
        g = json.load(fh)
    meta = g.get("meta", {})
    objs = [n for n in g["nodes"] if n.get("kind") == "object"]
    if not objs:
        raise SystemExit("no object nodes in %s" % a.graph)
    if not any("escapeReasons" in n for n in objs):
        raise SystemExit(
            "%s carries no escapeReasons. It was produced from a run with no .reasons file, "
            "i.e. by an uninstrumented Stava. Re-run the analysis with the instrumented "
            "build; do not draw these figures from a graph that cannot support them."
            % a.graph)

    os.makedirs(os.path.dirname(os.path.abspath(a.out_prefix)), exist_ok=True)
    if a.only in (None, "1"):
        figure1(objs, meta, a.title + " — escape-reason set clusters",
                a.top_reason_sets,
                a.out_prefix + "-clusters.svg", a.out_prefix + "-clusters.dot")
    if a.only in (None, "2"):
        figure2(objs, meta, a.title + " — escape-reason multiplicity",
                a.out_prefix + "-multiplicity.svg", a.out_prefix + "-multiplicity.dot")
    if a.only in (None, "3"):
        figure3(objs, meta, a.title + " — single-reason attribution",
                a.out_prefix + "-single.svg", a.out_prefix + "-single.dot")


if __name__ == "__main__":
    main()
