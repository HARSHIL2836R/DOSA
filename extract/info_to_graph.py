#!/usr/bin/env python3
"""
info_to_graph.py — Stava .info files -> graph.json

This file is the interface (PTA-Task-List task 6). Everything downstream reads graph.json,
never Stava's in-memory state and never the .info files.

WHAT IT READS
-------------
Each run writes one <Class>.info per declaring class into the output directory. Main.java
calls printAllInfo TWICE, appending: once on the pre-resolution summaries and once on the
resolved ones. So every method appears twice in its file:

    <sig>          <- occurrence 1: PTG + summary WITH conditional values   (the EDGES)
    <sig>          <- occurrence 2: PTG + summary with CVs replaced by
                                    Escape / NoEscape                       (the VERDICTS)

We take edges from occurrence 1 and escapeStatus from occurrence 2. Getting this backwards
yields a graph with no edges, or verdicts that are still unresolved.

FILTERING
---------
.info files are already partitioned one per declaring class, so restricting to application
classes is exact, not approximate: we read only the named classes' files. Everything else Soot
loaded is excluded. Edges whose TARGET is a non-application method are kept and pointed at a
library-boundary node, because dropping them would hide real dependencies.

PROVENANCE
----------
  CONTAINMENT  object -> object, from the PTG `Fields:` map (a field store).
  ARGUMENT     object -> (callee, parameter), from a summary CV with isReal = [T].
  SINK         object -> Escape / NoEscape. NOT a dependency edge: it is the resolved verdict
               drawn so the figure shows where each object lands. Named separately from the
               four-value dependency enum on purpose.
  RETURN, UNIFICATION are in the enum and are not emitted by this corpus; they are kept so the
  schema does not change when a program that needs them is added.

Summary CVs with isReal = [F] are containment-DERIVED: propagateES copies the container's CVs
into the contained object with isReal flipped (makeFalseClone). They are recorded with
"derived": true and are not drawn, because the Fields: edge already shows that containment.

  CAUTION, measured on M01: ConditionalValue.hashCode() is built from (method, object,
  fieldList) and does NOT include isReal, while equals() compares hashcodes. So a false-clone
  that differs from an existing CV only in isReal is silently absorbed by the HashSet. The
  [T]/[F] marker is therefore LOSSY and must not be used as the primary source of containment.
  `Fields:` is the primary source.

ESCAPE REASONS  (added Phase 11)
--------------
An instrumented Stava additionally writes <dirname>.reasons into the same output directory,
one line per abstract object:

    <method signature>	<bci>	<objectType>	REASON,REASON,REASON	GROUP

joined here on exactly the key this module already uses to identify a node,
(method signature, bci, objectType). Objects with no reason appear with an EMPTY reason field,
so the zero bucket of the multiplicity histogram is measured rather than inferred from absence.

Patch 0004 adds a fifth column, GROUP, indexing <dirname>.via: the successors (each
`method|bci|objectType`) that a TRANSITIVE_SUCCESSOR or PARAM_ESCAPES_VIA_SUCCESSOR fired
through, stored once per resolver component. By default read_reasons
follows those pointers and replaces the two propagated reasons with the causes at the end of
the chain (mode "roots"); HEAPVIZ_REASON_MODE=raw gives the reasons as Stava recorded them.

Patch 0005 adds columns 6 and 7, OWN and OWNGROUP: the subset of the reasons that fired on the
object itself, and the successors its own propagated reasons fired through. The rest was stamped
on it by its resolver component. read_reasons returns a ReasonMap whose `.own` holds the split
(in the same mode), and the join adds ownReasons / inheritedReasons, both None for older runs.

The join is ADDITIVE. It adds escapeReasons / reasonCount / realReasonCount /
surrenderReasonCount to object and parameter nodes and changes nothing that was there before.
A run with no .reasons file produces exactly the graph.json it produced before, byte for byte
apart from those absent keys; that is asserted by --require-reasons being off by default.

EQUI-ESCAPE
-----------
  Definition S (default): two objects are equi-escape iff their resolved EscapeStatus sets are
    equal after purge(). Computed over the post-resolution half.
  Definition C: two objects are equi-escape iff they are in the same strongly connected
    component. Computed over CONTAINMENT edges, NOT over the summary-CV graph.

    Why the deviation from Clustering-Design 4 option A, which says "condense G_dep": in
    G_dep every edge terminates at a (callee method, parameter) node, because Stava realises
    containment by copying CVs rather than by an edge to the container. SCCs over G_dep alone
    are therefore all singletons within a method and definition C would be vacuous. The
    object-to-object structure lives in the PTG Fields: map. Flagged in every caption.

USAGE
-----
  python3 extract/info_to_graph.py \
      --info-dir build/out/M01-pye \
      --classes M01 Box Item Node \
      --class-dir build/M01 \
      --javap /home/harshil/jvm/jdk8u502-b07/bin/javap \
      --config "MarkStoreEscaping=false (patched)" \
      --jdk "Temurin 8u502-b07" \
      --out build/out/M01-pye/graph.json
"""

import argparse
import json
import os
import re
import subprocess
import sys

PROVENANCE = ("CONTAINMENT", "ARGUMENT", "RETURN", "UNIFICATION", "SINK")

# ---------------------------------------------------------------------------
# escape reasons
#
# SURRENDER mirrors EscapeReason.isSurrender() in the instrumented stava source
# (es/EscapeReason.java). It is duplicated here rather than parsed out of the Java because the
# Python side must be able to read a .reasons file without a Java tree in reach. read_reasons()
# fails loudly on any constant it does not know, so the two cannot drift silently.
# ---------------------------------------------------------------------------

REASONS_REAL = (
    "STATIC_FIELD_STORE",
    "STORE_UNTRACKED_BASE",
    "CONSTANT_STORE",
    "STORE_CASCADE_UNTYPED",
    "STATIC_FIELD_LOAD",
    "LOAD_UNTRACKED_BASE",
    "CONSTANT_OBJECT",
    "THREAD_REACHABLE_CLASS",
    "THROWN",
    "MONITOR",
    "NATIVE_BLACKLIST",
    "CAUGHT_EXCEPTION",
    "RETURNED",
    "ASSIGNED_TO_THIS_OR_PARAM",
    "PARAM_ESCAPES_VIA_SUCCESSOR",
    "TRANSITIVE_SUCCESSOR",
)

REASONS_SURRENDER = (
    "NO_BCI_OBJECT",
    "NO_BCI_METHOD",
    "NO_BCI_METHOD_AT_RESOLVER",
    "CALLER_ONLY_UNRESOLVABLE",
)

# Propagation, not cause: "a successor already escapes". Under patch 0004 every firing also
# records WHICH successor (<dirname>.via), and read_reasons(mode="roots") replaces these
# two with the causes found at the end of the pointer chain.
REASONS_PROPAGATED = ("TRANSITIVE_SUCCESSOR", "PARAM_ESCAPES_VIA_SUCCESSOR")

# Synthetic, never written by Stava: produced only by resolve_roots() when a chain cannot be
# followed to a cause. Counted with SURRENDER, because each says "the data cannot name a
# cause here", not "the program does this".
REASONS_GAP = (
    "SUCCESSOR_UNRECORDED",       # propagated reason with no pointer recorded
    "SUCCESSOR_NOT_IN_REASONS",   # pointer names an object that has no .reasons line
    "SUCCESSOR_WITHOUT_CAUSE",    # chain followed to its end, nothing but propagation found
)

# declaration order, which is also the order a Java EnumSet iterates and therefore the order
# the constants arrive in on each line
REASON_ORDER = {r: i for i, r in enumerate(REASONS_REAL + REASONS_SURRENDER + REASONS_GAP)}
SURRENDER = set(REASONS_SURRENDER) | set(REASONS_GAP)
STAVA_REASONS = set(REASONS_REAL) | set(REASONS_SURRENDER)


def find_reasons_file(info_dir, explicit=None):
    """Locate <dirname>.reasons. Returns None when the run was not instrumented."""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    cands = sorted(f for f in os.listdir(info_dir) if f.endswith(".reasons"))
    if not cands:
        return None
    if len(cands) > 1:
        print("warn: %d .reasons files in %s, using %s"
              % (len(cands), info_dir, cands[0]), file=sys.stderr)
    return os.path.join(info_dir, cands[0])


def _ordered(names):
    return sorted(set(names), key=lambda r: REASON_ORDER.get(r, 999))


class ReasonMap(dict):
    """{(method_sig, bci, objType): [REASON, ...]}, plus `.own`.

    `.own` has the same keys and holds the subset of each object's reasons that fired on the
    object itself (patch 0005); the rest were stamped on it by its resolver component. It is
    None when the run predates patch 0005 and the split is unknown. Being a dict, a ReasonMap
    is a drop-in for every caller that only wants the reasons.
    """
    own = None


def read_reasons(path, mode=None):
    """-> ReasonMap {(method_sig, bci, objType): [REASON, ...]}. Raises on an unknown constant.

    mode "roots" (default): TRANSITIVE_SUCCESSOR / PARAM_ESCAPES_VIA_SUCCESSOR are replaced by
      the causes their successor pointers lead to (resolve_roots). Needs patch 0004's GROUP
      column and the <dirname>.via beside the .reasons; without them it falls back to raw,
      loudly.
    mode "raw": the reasons exactly as Stava recorded them. Tools that audit the
      instrumentation itself, or walk propagation on their own (escape_blast), must use this.
    The default can be overridden with HEAPVIZ_REASON_MODE=raw|roots.

    Columns 6-7 (patch 0005), OWN and OWNGROUP, fill `.own` in the same mode: in roots mode an
    object's own propagated reasons are resolved through its own pointers only.
    """
    mode = mode or os.environ.get("HEAPVIZ_REASON_MODE") or "roots"
    if mode not in ("raw", "roots"):
        raise SystemExit("unknown reason mode %r (want raw or roots)" % mode)
    out, group_of, unknown = {}, {}, set()
    own, own_group_of = {}, {}
    has_group_column = has_own_columns = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            ogrp = ""
            owns = None
            if len(parts) == 7:
                has_group_column = has_own_columns = True
                sig, bci, objtype, rs, grp, owns, ogrp = parts
            elif len(parts) == 5:
                has_group_column = True
                sig, bci, objtype, rs, grp = parts
            elif len(parts) == 4:
                sig, bci, objtype, rs = parts
                grp = ""
            else:
                print("warn: malformed .reasons line: %r" % line[:120], file=sys.stderr)
                continue
            names = [r for r in rs.split(",") if r]
            onames = [r for r in owns.split(",") if r] if owns is not None else []
            for r in names + onames:
                if r not in STAVA_REASONS:
                    unknown.add(r)
            try:
                key = (sig, int(bci), objtype)
                g = int(grp) if grp else None
                og = int(ogrp) if ogrp else None
            except ValueError:
                print("warn: unparseable bci or group in .reasons line: %r" % line[:120],
                      file=sys.stderr)
                continue
            # a method can legitimately appear twice; union rather than overwrite
            out[key] = _ordered(set(out.get(key, ())) | set(names))
            if g is not None:
                group_of.setdefault(key, set()).add(g)
            if owns is not None:
                own[key] = _ordered(set(own.get(key, ())) | set(onames))
            if og is not None:
                own_group_of.setdefault(key, set()).add(og)
    if unknown:
        raise SystemExit(
            "unknown escape reason(s) in %s: %s\n"
            "The Python tables in extract/info_to_graph.py have drifted from "
            "es/EscapeReason.java. Fix the tables; do not widen them silently."
            % (path, ", ".join(sorted(unknown))))
    LAST_REASONS_READ.clear()
    LAST_REASONS_READ.update(file=os.path.basename(path), requested=mode, mode="raw",
                             split=has_own_columns)

    def result(reasons, own_reasons):
        m = ReasonMap(reasons)
        m.own = own_reasons if has_own_columns else None
        return m

    if mode == "raw":
        return result(out, own)
    via_path = path[:-len(".reasons")] + ".via" if path.endswith(".reasons") else None
    if not has_group_column or not via_path or not os.path.exists(via_path):
        print("warn: %s has no successor-pointer data (written before patch 0004, or its .via "
              "is missing); propagated reasons cannot be resolved to causes, so they are "
              "reported RAW" % os.path.basename(path), file=sys.stderr)
        LAST_REASONS_READ["fallback"] = True
        return result(out, own)
    groups = read_via(via_path)
    if has_own_columns:
        roots, stats, own_roots = resolve_roots(out, group_of, groups, own, own_group_of)
    else:
        (roots, stats), own_roots = resolve_roots(out, group_of, groups), None
    print("reasons: mode=roots, %d objects carried a propagated reason and now carry its "
          "causes; gaps: %s%s" % (stats["propagated"],
                                  ", ".join("%s %d" % (g, stats[g]) for g in REASONS_GAP),
                                  "; own-vs-inherited split recorded" if has_own_columns
                                  else "; no own-vs-inherited split (run predates patch 0005)"),
          file=sys.stderr)
    LAST_REASONS_READ.update(mode="roots", stats=stats)
    return result(roots, own_roots)


# What the most recent read_reasons call actually did, so graph meta and figure captions can
# say it rather than leave the reader to guess which mode produced a number.
LAST_REASONS_READ = {}


def describe_reasons():
    """One caption-ready sentence for the most recent read_reasons call."""
    r = LAST_REASONS_READ
    if not r:
        return "not read"
    if r["mode"] == "roots":
        return ("%s, roots mode: TRANSITIVE_SUCCESSOR and PARAM_ESCAPES_VIA_SUCCESSOR replaced "
                "by the nearest causes they point to (patch 0004)" % r["file"])
    if r.get("fallback"):
        return ("%s, RAW: roots mode was requested but the run has no successor pointers, so "
                "TRANSITIVE_SUCCESSOR and PARAM_ESCAPES_VIA_SUCCESSOR are counted as reasons"
                % r["file"])
    return ("%s, raw mode: reasons as Stava recorded them, TRANSITIVE_SUCCESSOR and "
            "PARAM_ESCAPES_VIA_SUCCESSOR included" % r["file"])


def read_via(path):
    """<dirname>.via -> {group: {(method_sig, bci, objType), ...}}; a group may be empty."""
    groups = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            g, _, ptrs = line.partition("\t")
            s = groups.setdefault(int(g), set())
            for v in ptrs.split(";"):
                if v:
                    vsig, vbci, vtype = v.rsplit("|", 2)
                    s.add((vsig, int(vbci), vtype))
    return groups


def resolve_roots(names, group_of, groups, own=None, own_group_of=None):
    """Replace propagated reasons with the NEAREST causes their successor pointers lead to.

    Returns (roots, stats), or (roots, stats, own_roots) when `own` is given.

    For an object o carrying a propagated reason:

        roots(o)   = direct(o)  U  cause(s) for every successor s in o's pointer groups
        cause(s)   = direct(s)                        if s has a direct reason
                   = U cause(s') over s's pointers    otherwise

    direct(x) is x's reason set minus REASONS_PROPAGATED. A chain stops at the first object
    that has a cause of its own: that object escapes because of its direct reasons, and any
    further propagated route it also has is not why its predecessor escapes.

    WHY NEAREST AND NOT EVERY REACHABLE CAUSE. Following every pointer to the end was tried
    first. Pointer cycles pass through objects that escaped intraprocedurally, so the closure
    merged the JDK's large components into one blob: on avrora, 959 application objects came
    out with 11 reasons each, against 541 objects at 6 under raw reasons. Every application
    object whose raw reasons are only propagated reaches a direct cause within 4 hops
    (601 in 1, 138 in 2, 34 in 3, 1 in 4), so stopping there loses nothing a chain needs.

    A group is a node of its own (object -> group -> successors), so N members sharing P
    pointers cost N + P edges rather than N x P. Chains through objects with no direct reason
    can still cycle, so the fold runs over the SCC condensation.

    An object with no propagated reason is returned unchanged. A chain that cannot be followed
    yields one of REASONS_GAP rather than an empty set, so Escape still implies a non-empty
    reason set.

    OWN ROOTS (patch 0005). An object's own reasons resolve the same way through its OWN
    pointers, with one difference: a pointer to a sibling in the same resolver component (same
    union group) resolves to the sibling's own direct reasons, because at the moment it fired
    the sibling had escaped only for those; resolving it to the component union would hand the
    whole union back as "own" and undo the split. Own roots are a subset of roots by
    construction; stats["own_not_subset"] counts any object where that fails, and such an
    object's own roots are clipped to its roots.
    """
    prop = set(REASONS_PROPAGATED)
    direct, adj = {}, {}
    stats = {"propagated": 0, "own_not_subset": 0}
    stats.update({g: 0 for g in REASONS_GAP})

    for g, ptrs in groups.items():
        gn = ("#via", g)
        direct[gn] = set()
        for t in ptrs:
            if t in names:
                adj.setdefault(gn, set()).add(t)
            else:
                direct[gn].add("SUCCESSOR_NOT_IN_REASONS")

    obj_groups = {}
    for k, rs in names.items():
        d = set(rs) - prop
        direct[k] = d
        if not prop & set(rs):
            continue
        stats["propagated"] += 1
        gs = [("#via", g) for g in (group_of.get(k) or ()) if g in groups]
        if len(gs) < len(group_of.get(k) or ()) or not gs:
            d.add("SUCCESSOR_UNRECORDED")
        obj_groups[k] = gs
        if not set(rs) - prop:
            # no cause of its own: a chain that reaches this object continues through it
            for gn in gs:
                adj.setdefault(k, set()).add(gn)

    verts = sorted(set(adj) | {t for ts in adj.values() for t in ts})
    comp = tarjan_scc(verts, adj)
    members = {}
    for v, c in comp.items():
        members.setdefault(c, []).append(v)

    # Tarjan numbers an SCC only after every SCC it reaches, so ascending id is successor-first.
    # An OBJECT successor whose chain found nothing contributes SUCCESSOR_WITHOUT_CAUSE; an
    # empty GROUP contributes nothing, because its reason fired inside its own component,
    # which already carries those causes.
    acc_of = {}
    for c in sorted(members):
        acc = set()
        for v in members[c]:
            acc |= direct[v]
            for t in adj.get(v, ()):
                if comp[t] == c:
                    continue
                sub = acc_of[comp[t]]
                if not sub and t[0] != "#via":
                    sub = {"SUCCESSOR_WITHOUT_CAUSE"}
                acc |= sub
        acc_of[c] = acc

    def acc(x):
        return acc_of[comp[x]] if x in comp else direct[x]

    out = {}
    for k, rs in names.items():
        if k not in obj_groups:
            out[k] = list(rs)
            continue
        r = set(direct[k])
        for gn in obj_groups[k]:
            r |= acc(gn)
        if not r:
            r = {"SUCCESSOR_WITHOUT_CAUSE"}
        for g in REASONS_GAP:
            if g in r:
                stats[g] += 1
        out[k] = _ordered(r)
    if own is None:
        return out, stats

    own_out = {}
    for k, os_ in own.items():
        o = set(os_)
        if not prop & o:
            own_out[k] = _ordered(o)
            continue
        r = o - prop
        gids = own_group_of.get(k) or ()
        if not gids or any(g not in groups for g in gids):
            r.add("SUCCESSOR_UNRECORDED")
        mine = group_of.get(k) or set()
        for g in gids:
            for t in groups.get(g, ()):
                if t not in names:
                    r.add("SUCCESSOR_NOT_IN_REASONS")
                    continue
                if mine and (group_of.get(t) or set()) & mine:
                    sub = set(own.get(t, ())) - prop          # sibling: its own direct reasons
                else:
                    sub = acc(t)
                r |= sub or {"SUCCESSOR_WITHOUT_CAUSE"}
        if not r:
            r = {"SUCCESSOR_WITHOUT_CAUSE"}
        whole = set(out.get(k, ()))
        if not r <= whole:
            stats["own_not_subset"] += 1
            r &= whole
        own_out[k] = _ordered(r)
    return out, stats, own_out


def reason_fields(names, own=None):
    """The additive node fields, from a list of reason names and, since patch 0005, the subset
    that fired on the object itself. `own` None means the split is unknown (an older run): the
    two split fields are then None, which is not the same as "nothing inherited"."""
    names = list(names)
    return {
        "escapeReasons": names,
        "reasonCount": len(names),
        "realReasonCount": sum(1 for r in names if r not in SURRENDER),
        "surrenderReasonCount": sum(1 for r in names if r in SURRENDER),
        "ownReasons": None if own is None else [r for r in names if r in set(own)],
        "inheritedReasons": None if own is None else [r for r in names if r not in set(own)],
    }


def own_of(reasons, key):
    """The own list for key from a ReasonMap, or None when the run records no split."""
    o = getattr(reasons, "own", None)
    return None if o is None else o.get(key, [])


def reason_set_clusters(objs, top=20):
    """Group objects by their EXACT reason set — figure 1's data.

    objs: dicts already carrying escapeReasons (use reason_fields to guarantee the key).
    Returns (clusters, other) where each cluster is

        {"reasons": [...], "reasonCount": n, "realReasonCount": n,
         "surrenderReasonCount": n, "hasSurrender": bool, "count": members}

    ordered by reasonCount then descending member count, exactly as figure 1 specifies. The
    tail beyond `top` is aggregated into one entry whose member count is carried, never
    dropped: an "other" bucket with no number on it is how a figure lies about its own
    coverage.
    """
    groups, inherited = {}, {}
    # the own/inherited split is known only if every object carries it (patch 0005)
    split = bool(objs) and all(n.get("ownReasons") is not None for n in objs)
    for n in objs:
        k = tuple(n.get("escapeReasons") or [])
        groups[k] = groups.get(k, 0) + 1
        if split and n.get("inheritedReasons"):
            inherited[k] = inherited.get(k, 0) + 1

    def entry(k, c):
        return {
            # objects in the set carrying >=1 reason inherited from their resolver component;
            # None when the run records no split
            "inheritedCount": inherited.get(k, 0) if split else None,
            "reasons": list(k),
            "reasonCount": len(k),
            "realReasonCount": sum(1 for r in k if r not in SURRENDER),
            "surrenderReasonCount": sum(1 for r in k if r in SURRENDER),
            "hasSurrender": any(r in SURRENDER for r in k),
            "count": c,
        }

    allc = [entry(k, c) for k, c in groups.items()]
    # by population first, to decide who makes the top N ...
    by_pop = sorted(allc, key=lambda e: (-e["count"], e["reasonCount"], e["reasons"]))
    keep, tail = by_pop[:top], by_pop[top:]
    # ... then in the order the figure draws them
    keep.sort(key=lambda e: (e["reasonCount"], -e["count"], e["reasons"]))

    other = None
    if tail:
        other = {
            "reasons": None,
            "reasonCount": None,
            "realReasonCount": None,
            "surrenderReasonCount": None,
            "hasSurrender": any(e["hasSurrender"] for e in tail),
            "count": sum(e["count"] for e in tail),
            "inheritedCount": sum(e["inheritedCount"] for e in tail) if split else None,
            "distinctSets": len(tail),
        }
    return keep, other


def attach_reasons(nodes, reasons, key_of):
    """Stamp the four fields onto every node the .reasons file mentions.

    Nodes not mentioned get the fields with an empty list, so downstream code never has to
    distinguish "no reasons" from "not instrumented" per node - that distinction is made once,
    at the file level, by find_reasons_file.
    """
    hit = 0
    for n in nodes:
        k = key_of(n)
        if k is None:
            continue
        names = reasons.get(k)
        if names is None:
            n.update(reason_fields([], None if getattr(reasons, "own", None) is None else []))
        else:
            n.update(reason_fields(names, own_of(reasons, k)))
            hit += 1
    return hit


# ---------------------------------------------------------------------------
# bracket-aware splitting
#
# The .info file is Java Map.toString() output, so values nest: a conditional value
# <<M01: void f(int,int)>,<internal,8>.next,[T]> contains commas inside <>, () and [].
# A naive split(",") corrupts every one of them.
# ---------------------------------------------------------------------------

OPEN = {"<": ">", "(": ")", "[": "]", "{": "}"}
CLOSE = {v: k for k, v in OPEN.items()}


def split_top(s, sep=","):
    """Split s on sep, ignoring separators nested inside <>, (), [] or {}."""
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def strip_outer(s, o="<", c=">"):
    s = s.strip()
    if s.startswith(o) and s.endswith(c):
        return s[1:-1]
    return s


def split_map(body):
    """Split a Java map body 'k=v, k=v' into [(k, v)], bracket-aware on both sides."""
    pairs = []
    for item in split_top(body):
        depth, idx = 0, -1
        for i, ch in enumerate(item):
            if ch in OPEN:
                depth += 1
            elif ch in CLOSE:
                depth -= 1
            elif ch == "=" and depth == 0:
                idx = i
                break
        if idx < 0:
            continue
        pairs.append((item[:idx].strip(), item[idx + 1:].strip()))
    return pairs


# ---------------------------------------------------------------------------
# .info parsing
# ---------------------------------------------------------------------------

class MethodBlock:
    __slots__ = ("sig", "vars_raw", "fields_raw", "summary_raw")

    def __init__(self, sig):
        self.sig = sig
        self.vars_raw = "{}"
        self.fields_raw = "{}"
        self.summary_raw = "{}"


def parse_info(path):
    """Return the list of method blocks in file order (each method appears twice)."""
    blocks, cur, state = [], None, None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("<") and line.endswith(">") and ": " in line:
                cur = MethodBlock(line)
                blocks.append(cur)
                state = None
            elif cur is None:
                continue
            elif line == "PTG:":
                state = "ptg"
            elif line == "Summary":
                state = "summary"
            elif state == "ptg" and line.startswith("Vars:"):
                cur.vars_raw = line[len("Vars:"):]
            elif state == "ptg" and line.startswith("Fields:"):
                cur.fields_raw = line[len("Fields:"):]
            elif state == "summary" and line.startswith("{"):
                cur.summary_raw = line
    return blocks


def split_passes(blocks):
    """Split method blocks into (pre_resolution, post_resolution) dicts keyed by signature.

    Main.printAllInfo appends the whole map twice, so the FIRST occurrence of a signature is
    pre-resolution and the SECOND is post-resolution.
    """
    pre, post = {}, {}
    for b in blocks:
        if b.sig not in pre:
            pre[b.sig] = b
        elif b.sig not in post:
            post[b.sig] = b
    return pre, post


OBJ_RE = re.compile(r"^<(internal|external|argument|parameter|returnValue),(-?\d+)>$")


def parse_objref(tok):
    """'<internal,8>' -> ('internal', 8). Returns None if not an object reference."""
    m = OBJ_RE.match(tok.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def parse_cv(tok):
    """Parse one escape state token.

    Returns ('Escape', None) | ('NoEscape', None) | ('CV', dict) | (None, None).
    A CV prints as  <method,<objtype,ref>.f1.f2,[T]>  with method possibly the word 'caller'.
    """
    tok = tok.strip()
    if tok == "Escape":
        return "Escape", None
    if tok == "NoEscape":
        return "NoEscape", None
    if not (tok.startswith("<") and tok.endswith(">")):
        return None, None
    parts = split_top(strip_outer(tok))
    if len(parts) != 3:
        return None, None
    method, objpath, realtok = parts
    is_real = realtok.strip() == "[T]"

    # objpath is '<objtype,ref>' followed by zero or more '.field'
    if not objpath.startswith("<"):
        return None, None
    depth, end = 0, -1
    for i, ch in enumerate(objpath):
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None, None
    objtok, rest = objpath[:end + 1], objpath[end + 1:]
    ref = parse_objref(objtok)
    if ref is None:
        return None, None
    fields = [f for f in rest.split(".") if f]
    return "CV", {
        "method": method.strip(),
        "objType": ref[0],
        "objRef": ref[1],
        "fieldPath": fields,
        "isReal": is_real,
    }


def parse_fields(raw):
    """'{<internal,0>={<Box: Item item>=[<internal,8>]}}' -> [(0, 'item', 8), ...]"""
    edges = []
    for owner_tok, fieldmap in split_map(strip_outer(raw, "{", "}")):
        owner = parse_objref(owner_tok)
        if owner is None:
            continue
        for field_tok, targets in split_map(strip_outer(fieldmap, "{", "}")):
            # '<Box: Item item>' -> 'item'
            fname = strip_outer(field_tok).split()[-1] if field_tok.startswith("<") else field_tok
            for t in split_top(strip_outer(targets, "[", "]")):
                tgt = parse_objref(t)
                if tgt is not None:
                    edges.append((owner, fname, tgt))
    return edges


# ---------------------------------------------------------------------------
# javap: (class, method, bci) -> allocated Java type
# ---------------------------------------------------------------------------

JAVAP_NEW = re.compile(r"^\s*(\d+):\s+new\s+#\d+\s+//\s+class\s+(\S+)")
JAVAP_METHOD = re.compile(r"^\s{2}\S.*[;)]\s*$")


def javap_type_map(javap, class_dir, classes):
    """Map (className, methodName, bci) -> allocated type, by reading javap -c output."""
    out = {}
    for cls in classes:
        try:
            txt = subprocess.run(
                [javap, "-c", "-p", "-cp", class_dir, cls],
                capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("warn: javap failed for %s (%s); node types will be unknown" % (cls, e),
                  file=sys.stderr)
            continue
        method = None
        for line in txt.splitlines():
            m = JAVAP_NEW.match(line)
            if m and method:
                out[(cls, method, int(m.group(1)))] = m.group(2).replace("/", ".")
                continue
            if line.startswith("    "):
                continue
            if JAVAP_METHOD.match(line) and "{" not in line:
                sig = line.strip().rstrip(";")
                head = sig.split("(")[0].strip()
                name = head.split()[-1] if head.split() else ""
                # a constructor prints as 'public M01()' - no return type before the name
                method = "<init>" if name == cls or name.endswith("." + cls) else name
    return out


def soot_sig_parts(sig):
    """'<M01: void main(java.lang.String[])>' -> ('M01', 'main')."""
    inner = strip_outer(sig)
    cls, rest = inner.split(":", 1)
    head = rest.strip().split("(")[0].strip()
    name = head.split()[-1] if head.split() else ""
    return cls.strip(), name


# ---------------------------------------------------------------------------
# graph construction
# ---------------------------------------------------------------------------

def build(info_dir, classes, typemap, config, jdk, definition, reasons=None):
    nodes, edges = {}, []
    app = set(classes)

    def nid(kind, method, ref=None, objtype=None):
        if kind == "sink":
            return "sink:" + method
        return "%s|%s|%s" % (objtype or "obj", method, ref)

    def ensure(node_id, **kw):
        if node_id not in nodes:
            nodes[node_id] = dict(id=node_id, **kw)
        return nodes[node_id]

    ensure(nid("sink", "Escape"), kind="sink", method=None, bci=None, type="Escape",
           isReal=None, label="Escape", escapeStatus="Escape")
    ensure(nid("sink", "NoEscape"), kind="sink", method=None, bci=None, type="NoEscape",
           isReal=None, label="NoEscape", escapeStatus="NoEscape")

    for cls in sorted(classes):
        path = os.path.join(info_dir, cls + ".info")
        if not os.path.exists(path):
            print("warn: no .info for application class %s" % cls, file=sys.stderr)
            continue
        pre, post = split_passes(parse_info(path))

        for sig in sorted(pre):
            decl_cls, mname = soot_sig_parts(sig)
            pre_b = pre[sig]
            post_b = post.get(sig)

            # ---- nodes: every object key in the pre-resolution summary
            for key_tok, _val in split_map(strip_outer(pre_b.summary_raw, "{", "}")):
                ref = parse_objref(key_tok)
                if ref is None:
                    continue
                objtype, num = ref
                kind = "object" if objtype in ("internal", "external") else "param"
                jtype = typemap.get((decl_cls, mname, num), objtype) if kind == "object" \
                    else objtype
                label = "%s@%s.%s:%d" % (jtype, decl_cls, mname, num)
                ensure(nid("obj", sig, num, objtype), kind=kind, method=sig, bci=num,
                       type=jtype, isReal=None, label=label, sootNode=key_tok,
                       escapeStatus=None)

            # ---- escapeStatus from the POST-resolution half
            if post_b is not None:
                for key_tok, val in split_map(strip_outer(post_b.summary_raw, "{", "}")):
                    ref = parse_objref(key_tok)
                    if ref is None:
                        continue
                    states = sorted(
                        t.strip() for t in split_top(strip_outer(val, "[", "]")))
                    n = nodes.get(nid("obj", sig, ref[1], ref[0]))
                    if n is not None:
                        n["escapeStatus"] = ",".join(states) if states else "unknown"

            # ---- CONTAINMENT edges from the PTG Fields: map
            for owner, fname, tgt in parse_fields(pre_b.fields_raw):
                a = nid("obj", sig, owner[1], owner[0])
                b = nid("obj", sig, tgt[1], tgt[0])
                if a in nodes and b in nodes:
                    edges.append(dict(fromNode=a, toNode=b, fieldPath=[fname],
                                      provenance="CONTAINMENT", derived=False))

            # ---- ARGUMENT edges from pre-resolution CVs
            for key_tok, val in split_map(strip_outer(pre_b.summary_raw, "{", "}")):
                ref = parse_objref(key_tok)
                if ref is None:
                    continue
                src = nid("obj", sig, ref[1], ref[0])
                for tok in split_top(strip_outer(val, "[", "]")):
                    kind, cv = parse_cv(tok)
                    if kind != "CV":
                        continue
                    tgt_cls = cv["method"]
                    if tgt_cls != "caller":
                        tcls, tname = soot_sig_parts(tgt_cls) \
                            if tgt_cls.startswith("<") else (tgt_cls, "")
                    else:
                        tcls, tname = "caller", ""
                    tgt_id = nid("obj", tgt_cls, cv["objRef"], cv["objType"])
                    if tgt_id not in nodes:
                        in_app = tcls in app
                        where = ("%s.%s" % (tcls, tname)) if tname else tcls
                        lbl = "%s@%s:%s" % (cv["objType"], where, cv["objRef"])
                        ensure(tgt_id, kind="param", method=tgt_cls, bci=cv["objRef"],
                               type=cv["objType"], isReal=None, label=lbl,
                               sootNode="<%s,%s>" % (cv["objType"], cv["objRef"]),
                               escapeStatus=None, libraryBoundary=not in_app)
                    # A returnValue target is a RETURN edge regardless of isReal. Stava
                    # prints these with [F] (ConditionalValue.getRetCV builds them without
                    # the isReal flag set), so keying purely on isReal would mislabel every
                    # return as derived containment.
                    if cv["objType"] == "returnValue":
                        prov, derived = "RETURN", False
                    elif cv["isReal"]:
                        prov, derived = "ARGUMENT", False
                    else:
                        prov, derived = "CONTAINMENT", True
                    edges.append(dict(fromNode=src, toNode=tgt_id,
                                      fieldPath=cv["fieldPath"],
                                      provenance=prov, derived=derived,
                                      isReal=cv["isReal"]))

    # ---- SINK edges from the resolved verdict
    for n in list(nodes.values()):
        if n["kind"] == "sink" or not n.get("escapeStatus"):
            continue
        st = n["escapeStatus"]
        if st in ("Escape", "NoEscape"):
            edges.append(dict(fromNode=n["id"], toNode=nid("sink", st), fieldPath=[],
                              provenance="SINK", derived=False))

    # ---- Definition S: equal resolved status
    s_key, s_ids = {}, {}
    for n in sorted(nodes.values(), key=lambda x: x["id"]):
        if n["kind"] == "sink":
            continue
        k = n.get("escapeStatus") or "unresolved"
        if k not in s_ids:
            s_ids[k] = len(s_ids)
        s_key[n["id"]] = s_ids[k]

    # ---- Definition C: SCC over CONTAINMENT edges (Tarjan, iterative)
    adj = {}
    for e in edges:
        if e["provenance"] == "CONTAINMENT" and not e["derived"]:
            adj.setdefault(e["fromNode"], []).append(e["toNode"])
    c_key = tarjan_scc([n["id"] for n in sorted(nodes.values(), key=lambda x: x["id"])
                        if n["kind"] != "sink"], adj)

    for n in nodes.values():
        if n["kind"] == "sink":
            n["equiEscapeSetS"] = None
            n["equiEscapeSetC"] = None
            n["equiEscapeSet"] = None
        else:
            n["equiEscapeSetS"] = s_key.get(n["id"])
            n["equiEscapeSetC"] = c_key.get(n["id"])
            n["equiEscapeSet"] = n["equiEscapeSetS"] if definition == "S" \
                else n["equiEscapeSetC"]

    # ---- escape reasons, additive, joined on (method, bci, objectType) ------------
    # Sinks have no method and no bci, so they are never keyed and never stamped.
    def reason_key(n):
        if n["kind"] == "sink" or n.get("method") is None or n.get("bci") is None:
            return None
        objtype = n.get("sootNode")
        if objtype and objtype.startswith("<") and "," in objtype:
            objtype = objtype[1:].split(",", 1)[0]
        else:
            objtype = n.get("type")
        return (n["method"], n["bci"], objtype)

    if reasons is not None:
        attach_reasons(list(nodes.values()), reasons, reason_key)

    # deterministic ordering
    node_list = sorted(nodes.values(), key=lambda x: x["id"])
    edge_list = sorted(edges, key=lambda e: (e["fromNode"], e["toNode"],
                                             e["provenance"], str(e["fieldPath"])))
    seen, uniq = set(), []
    for e in edge_list:
        k = (e["fromNode"], e["toNode"], e["provenance"], tuple(e["fieldPath"]))
        if k not in seen:
            seen.add(k)
            uniq.append(e)

    return {
        "meta": {
            "jdk": jdk,
            "config": config,
            "filter": "application classes only: " + ", ".join(sorted(classes)),
            "definition": definition,
            "definitionS": "equal resolved EscapeStatus after purge()",
            "definitionC": "same SCC over CONTAINMENT edges (PTG Fields:), "
                           "not over the summary-CV graph - see extract/info_to_graph.py",
            "provenanceEnum": list(PROVENANCE),
            "source": "pre-resolution half of .info for edges; "
                      "post-resolution half for escapeStatus",
            "reasons": ("joined on (method, bci, objectType) from " + describe_reasons()
                        if reasons is not None else
                        "NOT AVAILABLE: this run was made by an uninstrumented Stava"),
        },
        "nodes": node_list,
        "edges": uniq,
    }


def tarjan_scc(vertices, adj):
    """Iterative Tarjan. Returns {vertex: scc_id}. Deterministic: inputs are pre-sorted."""
    index, low, on_stack, stack, result = {}, {}, set(), [], {}
    counter, scc_id = [0], [0]

    for root in vertices:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                on_stack.add(v)
            recursed = False
            succs = sorted(adj.get(v, []))
            for i in range(pi, len(succs)):
                w = succs[i]
                if w not in index:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if recursed:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    result[w] = scc_id[0]
                    if w == v:
                        break
                scc_id[0] += 1
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info-dir", required=True)
    ap.add_argument("--classes", nargs="+", required=True)
    ap.add_argument("--class-dir", default=None, help="dir of .class files, for javap")
    ap.add_argument("--javap", default="javap")
    ap.add_argument("--config", required=True)
    ap.add_argument("--jdk", required=True)
    ap.add_argument("--definition", choices=["S", "C"], default="S")
    ap.add_argument("--reasons", default=None,
                    help="path to <dirname>.reasons; default: the one in --info-dir")
    ap.add_argument("--require-reasons", action="store_true",
                    help="fail rather than silently emit a graph.json with no reason fields")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tmap = javap_type_map(a.javap, a.class_dir, a.classes) if a.class_dir else {}

    rpath = find_reasons_file(a.info_dir, a.reasons)
    if rpath is None:
        if a.require_reasons:
            raise SystemExit("no .reasons file in %s and --require-reasons was given"
                             % a.info_dir)
        reasons = None
        print("note: no .reasons file in %s; graph.json will carry no reason fields"
              % a.info_dir, file=sys.stderr)
    else:
        reasons = read_reasons(rpath)

    g = build(a.info_dir, a.classes, tmap, a.config, a.jdk, a.definition, reasons)

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(g, fh, indent=2, sort_keys=True)
        fh.write("\n")

    objs = [n for n in g["nodes"] if n["kind"] == "object"]
    cont = [e for e in g["edges"] if e["provenance"] == "CONTAINMENT" and not e["derived"]]
    arg = [e for e in g["edges"] if e["provenance"] == "ARGUMENT"]
    print("%s" % a.out)
    print("  objects            : %d" % len(objs))
    print("  NoEscape / Escape  : %d / %d" % (
        sum(1 for n in objs if n["escapeStatus"] == "NoEscape"),
        sum(1 for n in objs if n["escapeStatus"] == "Escape")))
    print("  containment edges  : %d" % len(cont))
    print("  argument edges     : %d" % len(arg))
    print("  sets under S       : %d" % len({n["equiEscapeSetS"] for n in objs}))
    print("  sets under C       : %d" % len({n["equiEscapeSetC"] for n in objs}))
    if reasons is not None:
        from collections import Counter
        cnt = Counter(n.get("reasonCount", 0) for n in objs)
        sets = {tuple(n.get("escapeReasons") or []) for n in objs}
        print("  reasons file       : %s" % rpath)
        print("  reasonCount hist   : %s"
              % ", ".join("%d reasons x%d" % (k, cnt[k]) for k in sorted(cnt)))
        print("  distinct reason sets: %d" % len(sets))
        bad = [n for n in objs
               if n.get("escapeStatus") == "Escape" and n.get("reasonCount") == 0]
        # the converse: the side map is append-only and the analysis is not, so a reason can
        # outlive the Escape that produced it. See Phase 11.
        retracted = [n for n in objs
                     if n.get("escapeStatus") == "NoEscape" and n.get("reasonCount")]
        print("  Escape with 0 reasons: %d   <- integrity check, see Phase 11" % len(bad))
        print("  NoEscape with reasons: %d   <- retracted by a later worklist iteration"
              % len(retracted))


if __name__ == "__main__":
    main()
