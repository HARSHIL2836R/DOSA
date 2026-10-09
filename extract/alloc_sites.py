#!/usr/bin/env python3
"""alloc_sites.py - fold Stava's objects onto allocation sites, with Spark (patch 0006).

Stava counts an object once per method that sees it: a call result or a field read is a fresh
`external` node in every method it reaches, so the reason figures counted about 4 nodes per
allocation site (Viz-Faithfulness-Audit, O1). Patch 0006 writes <dirname>.alloc: for every
internal and external node, the allocation sites Spark says it may be. This module turns that
into the figures' unit, fix F4:

  SITE     an application allocation site: an `internal` node whose unit is a new, newarray or
           multianewarray (.alloc KIND NEW), in a method of the named classes. Counted once.
  ALIAS    any other application node whose Spark set holds at least one application site:
           call results, field and array reads, and the internal element of a local array.
           It is not counted. Whether its reasons reach the site depends on the rule below.
  OUTSIDE  an application node that aliases no application site. Not counted, reported by
           cause: allocated only outside the application (library code, Spark's merged
           StringBuilder/StringBuffer node, its string-constant node), a constant, a caught
           exception, no set (method unreachable in Spark, no unit, no bci, empty set).

REASONS OF A SITE. Three rules, chosen by alias_max in fold() and by HEAPVIZ_ALIAS_REASONS in the
extractors (alias_rule()):
  own      (default) the site's own node's reasons only. The aliases are folded and not
           counted, but add no reason.
  single   plus the reasons of every alias whose Spark set names exactly this one site.
  union    plus the reasons of every alias whose set names this site among others.
The default is `own` because the other two count one escape twice. In roots mode the site's own
node already carries the causes Stava links to it in other frames (a returned object reaches its
caller's cause through the successor pointers), so an alias's reason usually restates one of
them from the alias's frame: STATIC_FIELD_LOAD in the frame that reads a static, on top of the
STATIC_FIELD_STORE the site carries. On avrora (MarkStoreEscaping=false) the union puts
STATIC_FIELD_LOAD on 525 sites, 411 of them only through an alias. Spark adds a second error on
top: it is context- and flow-insensitive, so an alias that names four sites is one object at a
time, not four, and its reason lands on all four. Single-reason share of escaping sites, avrora
false: own 70.7 %, single 52.1 %, union 36.7 %.

In every rule a site Stava leaves NoEscape takes no reason from an alias; that is counted as a
conflict. A NoEscape site has no escaping alias if Stava and Spark are both exact, so an escaping
alias of one means Spark's set is wider than the object's, and adding its reasons would draw a
stack-allocated site as escaping.
"""
import os
from collections import Counter, defaultdict

from info_to_graph import SURRENDER

ALIAS_KINDS = ("PTS",)
OUTSIDE_KIND = {"CONST": "constant", "CAUGHT": "caught exception", "NOBCI": "no bci",
                "UNREACHABLE": "method unreachable in Spark", "NOUNIT": "no defining unit"}


RULES = {"own": 0, "single": 1, "union": None}


def alias_rule():
    """(name, alias_max) from HEAPVIZ_ALIAS_REASONS: own (default), single or union."""
    name = os.environ.get("HEAPVIZ_ALIAS_REASONS", "own")
    if name not in RULES:
        raise SystemExit("HEAPVIZ_ALIAS_REASONS=%s: expected one of %s" % (name, ", ".join(RULES)))
    return name, RULES[name]


RULE_TEXT = {"own": "each site carries its own node's reasons only; aliases are folded and "
                    "add none",
             "single": "each site carries its own node's reasons plus those of aliases whose "
                       "Spark set names only that site",
             "union": "each site carries its own node's reasons plus those of every alias whose "
                      "Spark set names it, which is context-insensitive"}


def find_alloc_file(info_dir):
    fs = sorted(f for f in os.listdir(info_dir) if f.endswith(".alloc"))
    return os.path.join(info_dir, fs[0]) if fs else None


def read_alloc(path):
    """-> ({(method, bci, objType): (KIND, [site, ...])}, n_sets). A site is (method, bci, type)
    for a site in a method body, else the token string (@STRING, @MERGED:..., ...)."""
    sets = {}
    with open(path[:-len(".alloc")] + ".allocsets", encoding="utf-8") as fh:
        for line in fh:
            sid, _, body = line.rstrip("\n").partition("\t")
            out = []
            for s in body.split(";"):
                # A token can itself contain the separator: a class constant's descriptor,
                # @CLASS:[Ljava/lang/String; ends in ';'. The pieces after it rejoin the token.
                if not s:
                    continue
                if s.startswith("@"):
                    out.append(s)
                elif s.count("|") < 2 and out and isinstance(out[-1], str):
                    out[-1] += ";" + s
                else:
                    m, b, t = s.rsplit("|", 2)
                    out.append((m, int(b), t))
            sets[sid] = out
    kinds = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            kinds[(p[0], int(p[1]), p[2])] = (p[3], sets.get(p[4], []) if p[4] else [])
    return kinds, len(sets)


def fold(objs, alloc, is_app, alias_max=None):
    """objs: {key: node} over application object nodes (internal + external), each carrying
    escapeStatus and the reason fields (escapeReasons, ownReasons). alloc: read_alloc()[0].
    is_app(method_sig) -> bool.

    alias_max: an alias contributes its reasons only when its Spark set names at most this many
    application sites. None = every alias (the union rule); 0 = none (each site keeps its own
    node's reasons); 1 = only aliases that name exactly one site. Every alias is folded, counted
    as an alias, and kept out of the population whatever the rule.

    Returns (sites, stats, outside, outside_escaping). sites: {(method, bci): dict} with key,
    type, escapeStatus, reasons, own (None when the run has no split), aliases (count), aliasOnly
    (reasons that came only through aliases)."""
    stats = Counter()
    outside = Counter()
    outside_escaping = Counter()
    sites = {}
    split = any(n.get("ownReasons") is not None for n in objs.values())

    def escaping(n):
        return "Escape" in (n.get("escapeStatus") or "").split(",")

    for key, n in objs.items():
        kind, _s = alloc.get(key, ("MISSING", []))
        if kind == "NEW" and key[2] == "internal":
            sites[(key[0], key[1])] = dict(
                key=(key[0], key[1]), node=key, type=next((s[2] for s in _s if isinstance(s, tuple)),
                                                          "?"),
                escapeStatus=n.get("escapeStatus"), escaping=escaping(n),
                reasons=set(n.get("escapeReasons") or ()),
                own=set(n.get("ownReasons") or ()) if split else None,
                aliases=0, aliasOnly=set(), ambiguous=0)

    alias_sets = Counter()
    for key, n in objs.items():
        kind, sset = alloc.get(key, ("MISSING", []))
        if kind == "NEW" and key[2] == "internal":
            continue
        app = [(s[0], s[1]) for s in sset if isinstance(s, tuple) and is_app(s[0])]
        if kind in ALIAS_KINDS and app:
            stats["alias"] += 1
            alias_sets[min(len(app), 21)] += 1
            rs = set(n.get("escapeReasons") or ())
            own = set(n.get("ownReasons") or ())
            for sk in app:
                s = sites.get(sk)
                if s is None:
                    stats["alias target not a counted site"] += 1
                    continue
                s["aliases"] += 1
                if len(app) > 1:
                    s["ambiguous"] += 1
                if not rs:
                    continue
                if alias_max is not None and len(app) > alias_max:
                    stats["alias reasons not applied: alias names more than %s site(s)"
                          % alias_max] += 1
                    continue
                if not s["escaping"]:
                    stats["conflict: escaping alias of a NoEscape site (not applied)"] += 1
                    continue
                s["aliasOnly"] |= rs - s["reasons"]
                s["reasons"] |= rs
                if s["own"] is not None:
                    s["own"] |= own
            continue
        if kind in ALIAS_KINDS:
            if not sset:
                why = "empty Spark set"
            elif any(isinstance(s, tuple) for s in sset):
                why = "allocated only outside the application"
            elif all(isinstance(s, str) and s.startswith("@MERGED") for s in sset):
                why = "Spark's merged StringBuilder/StringBuffer node only"
            elif all(isinstance(s, str) and s == "@STRING" for s in sset):
                why = "string constants only"
            else:
                why = "Spark-made nodes only (merged, string, class, special)"
        else:
            why = OUTSIDE_KIND.get(kind, "no .alloc line" if kind == "MISSING" else kind)
        outside[why] += 1
        if escaping(n):
            outside_escaping[why] += 1

    for s in sites.values():
        if s["aliasOnly"]:
            stats["sites gaining a reason only through aliases"] += 1
            if s["ambiguous"]:
                stats["  of which some alias names several application sites"] += 1
    stats["sites"] = len(sites)
    stats["alias set size histogram"] = dict(sorted(alias_sets.items()))
    return sites, dict(stats), dict(outside), dict(outside_escaping)


def site_nodes(sites, order):
    """Sites as figure nodes: kind object plus the reason fields reason_figures reads."""
    out = []
    for k in sorted(sites):
        s = sites[k]
        names = sorted(s["reasons"], key=lambda r: order.get(r, 999))
        n = dict(id="site|%s|%d" % k, kind="object", method=k[0], bci=k[1], objType="site",
                 allocType=s["type"], escapeStatus=s["escapeStatus"], aliases=s["aliases"],
                 escapeReasons=names, reasonCount=len(names),
                 realReasonCount=sum(1 for r in names if r not in SURRENDER),
                 surrenderReasonCount=sum(1 for r in names if r in SURRENDER),
                 ownReasons=None if s["own"] is None else [r for r in names if r in s["own"]],
                 inheritedReasons=None if s["own"] is None
                 else [r for r in names if r not in s["own"]])
        out.append(n)
    return out
