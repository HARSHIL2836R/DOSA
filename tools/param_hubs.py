#!/usr/bin/env python3
"""param_hubs.py - allocation sites that escape through a parameter, and parameters that make
several allocation sites escape. Evidence for or against hoisting objects into an ancestor frame.

    python3 tools/param_hubs.py --run-dir /tmp/rv/p5out/avrora-false \
        --app-info-dir /tmp/rv/p5info/avrora-false --class-prefix avrora. \
        --label "avrora false" --json out.json

Needs a patch-0005 run: own reasons (column 6) and own successor pointers (column 7).

UNIT. Application allocation sites: `internal` nodes in methods of the named classes. An
external is a handle on an object allocated elsewhere and is reported only as a count.

ROUTES. An escaping allocation site o escapes THROUGH A PARAMETER when one of its OWN reasons does:
  down-ctor  own TRANSITIVE_SUCCESSOR/PARAM_ESCAPES_VIA_SUCCESSOR pointer to <init>'s `this`
  down-recv  ... pointer to another method's `this` (parameter -1)
  down-arg   ... pointer to a callee's parameter k >= 0
  up         own ASSIGNED_TO_THIS_OR_PARAM; the parameter is read from o's pre-resolution
             conditional value <caller,<argument,k>...> (k = -1 is `this`)
Own, not inherited: a reason stamped on o by its resolver component (patch 0005) fired on another
member and is counted as "inherited only", never as a route.

WHY THE PARAMETER ESCAPES, for hoisting. Each route names a parameter node p = (method, k); p's
resolved reasons (roots mode, every reason p carries) are classed:
  does not escape  p has no reason. Only possible on an up route: the container never escapes.
  frame-bounded    only RETURNED, ASSIGNED_TO_THIS_OR_PARAM, THROWN, CAUGHT_EXCEPTION, MONITOR:
                   p outlives its method but lives in a caller's frame, a caller-provided object,
                   or the stack until caught. MONITOR is not a lifetime escape at all.
  global           any static store/load, constant, thread-reachable class, native, untracked
                   store/load, or the store cascade: no frame on the stack bounds p.
  unknown          only surrender or SUCCESSOR_* gap constants.
An allocation site is a HOIST CANDIDATE when every one of its own reasons is a parameter route
and every route's parameter does not escape or is frame-bounded. That is an upper bound: a
frame-bounded parameter is bounded by ONE level; the ancestor it leads to is not checked further.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "extract"))
from benchmark_scale import build  # noqa: E402
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import (REASONS_PROPAGATED, SURRENDER, find_reasons_file,  # noqa: E402
                           read_reasons, read_via)

PROP = set(REASONS_PROPAGATED)
ASSIGNED = "ASSIGNED_TO_THIS_OR_PARAM"
FRAME_BOUNDED = {"RETURNED", ASSIGNED, "THROWN", "CAUGHT_EXCEPTION", "MONITOR"}
UNKNOWN = set(SURRENDER)


def classify(rs):
    rs = set(rs or ())
    if not rs:
        return "does not escape"
    real = rs - UNKNOWN
    if real - FRAME_BOUNDED:
        return "global"
    if real:
        return "frame-bounded"
    return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="whole-run patch-0005 output")
    ap.add_argument("--app-info-dir", required=True, help="application .info files")
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    rp = find_reasons_file(a.run_dir, None)
    raw = read_reasons(rp, mode="raw")
    roots = read_reasons(rp, mode="roots")
    if raw.own is None:
        raise SystemExit("%s predates patch 0005: no own reasons" % rp)
    via = read_via(rp[:-len(".reasons")] + ".via")
    own_group, union_group = {}, {}
    with open(rp, encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) == 7 and p[6]:
                own_group[(p[0], int(p[1]), p[2])] = int(p[6])
            if len(p) >= 5 and p[4]:
                union_group[(p[0], int(p[1]), p[2])] = int(p[4])

    def is_app(sig):
        q = parse_soot_sig(sig)
        return q is not None and any(q[0].startswith(x) for x in a.class_prefix)

    # up routes: <caller,<argument,k>> conditional values on application objects
    nodes, _he, dep_edges, _files = build(a.app_info_dir, a.class_prefix, None)
    up_params = defaultdict(set)
    arg_params = defaultdict(set)     # callee parameters an object is passed to (pre-resolution)
    for s, t, _prov in dep_edges:
        n = nodes.get(s)
        if n is None or n["objType"] not in ("internal", "external"):
            continue
        key = (n["method"], int(n["bci"]), n["objType"])
        if t.startswith("argument|caller|"):
            up_params[key].add(int(t.rsplit("|", 1)[1]))
        elif t.startswith("parameter|"):
            _ty, sig, ref = t.split("|", 2)
            arg_params[key].add((sig, int(ref), "parameter"))

    sites = [k for k in raw if k[2] == "internal" and is_app(k[0])]
    externals = sum(1 for k in raw if k[2] == "external" and is_app(k[0]))
    escaping = [k for k in sites if raw[k]]

    def trace(o):
        """Follow o's OWN escape through aliases to parameter routes.

        Starting from o, every own pointer to a parameter is a down route. A pointer to a
        non-parameter node (a caller's external holding o's value, a return slot) is an alias:
        the walk continues through the alias's own reasons and own pointers. An own
        ASSIGNED_TO_THIS_OR_PARAM on o or on an alias is an up route into that node's method's
        parameter. Any other own reason met on the way is a direct cause, kept with its class.
        Returns (routes, direct_reasons, unknown_up, inherited_alias)."""
        routes, direct = set(), set()
        unknown_up = inherited_alias = False
        seen, stack = {o}, [o]
        while stack:
            x = stack.pop()
            own = set(raw.own.get(x, ()))
            if x != o and not own and raw.get(x):
                inherited_alias = True
            # A callee parameter x is passed to that sits in x's own resolver component: the
            # argument edge and the parameter's caller edge are what closed the component, so
            # x escapes with that parameter even though no reason fired on x itself.
            gx = union_group.get(x)
            if gx is not None:
                for p in arg_params.get(x, ()):
                    if union_group.get(p) == gx and raw.get(p):
                        kind = ("down-ctor" if p[1] == -1 and ": void <init>(" in p[0] else
                                "down-recv" if p[1] == -1 else "down-arg")
                        routes.add((kind + " (component)", p))
            if ASSIGNED in own:
                ks = up_params.get(x)
                if ks:
                    routes.update(("up", (x[0], k, "parameter")) for k in ks)
                else:
                    unknown_up = True
            direct |= own - PROP - {ASSIGNED}
            if own & PROP:
                for t in via.get(own_group.get(x), ()):
                    if t[2] == "parameter":
                        kind = ("down-ctor" if t[1] == -1 and ": void <init>(" in t[0] else
                                "down-recv" if t[1] == -1 else "down-arg")
                        routes.add((kind, t))
                    elif t not in seen:
                        seen.add(t)
                        stack.append(t)
        return routes, direct, unknown_up, inherited_alias

    cat = Counter()
    route_kind = Counter()
    hub = defaultdict(lambda: {"objects": set(), "kinds": Counter(), "methods": set()})
    obj_routes = {}
    for o in escaping:
        routes, direct, unknown_up, inherited_alias = trace(o)
        if not raw.own.get(o) and not routes:
            cat["inherited only, no parameter in its component edges"] += 1
            continue
        if not routes and not unknown_up:
            # still worth knowing why: an object that escapes only by being returned or thrown
            # is the other frame-bounded population, outside this report's parameter question
            cat["no parameter route; own reasons %s" % (classify(direct) if direct
                                                      else "none recorded")] += 1
            continue
        obj_routes[o] = (routes, direct, unknown_up)
        for kind, p in routes:
            route_kind[kind] += 1
            h = hub[p]
            h["objects"].add(o)
            h["kinds"][kind] += 1
            h["methods"].add(o[0])
        dcls = classify(direct) if direct else None
        if not routes:
            cat["parameter route, parameter not recorded"] += 1
        elif dcls is None:
            cat["parameter routes only"] += 1
        elif dcls == "frame-bounded":
            cat["parameter routes + frame-bounded own reasons (returned, thrown, monitor)"] += 1
        else:
            cat["parameter routes + %s own reasons" % dcls] += 1

    # the objects each application caller passes to a parameter: the CONTAINER on an up route
    callers_of = defaultdict(set)
    for c, ps in arg_params.items():
        for p in ps:
            callers_of[p].add(c)

    SEVERITY = {"does not escape": 0, "frame-bounded": 1, "unknown": 2, "global": 3}

    def worst(classes):
        return max(classes, key=lambda c: SEVERITY[c]) if classes else "does not escape"

    def node_class(x, mode):
        """pessimistic: every reason x carries, component union included.
        optimistic: x's own roots when it has any, else the union (nothing better is known)."""
        if mode == "optimistic" and roots.own is not None and roots.own.get(x):
            return classify(roots.own.get(x))
        return classify(roots.get(x))

    no_app_caller = set()

    def route_class(kind, p, mode):
        c = node_class(p, mode)
        if kind == "up":
            # the stored object lives as long as the container a caller passed in, so the
            # callers' argument objects decide; the parameter node alone does not
            cs = callers_of.get(p)
            if cs:
                c = worst([c] + [node_class(x, mode) for x in cs])
            else:
                no_app_caller.add(p)
        return c

    rcls = {mode: {(k, p): route_class(k, p, mode) for o, (routes, *_r) in obj_routes.items()
                   for k, p in routes}
            for mode in ("pessimistic", "optimistic")}
    pcls = {p: worst([rcls["pessimistic"][(k, p)] for k in h["kinds"]]) for p, h in hub.items()}

    # hoist candidates: every route bounded or non-escaping, and every other own reason met on
    # the way frame-bounded too
    hoist = {m: Counter() for m in rcls}
    strict = {m: 0 for m in rcls}
    for mode in rcls:
        for o, (routes, direct, unknown_up) in obj_routes.items():
            if not routes:
                hoist[mode]["undecided: a parameter was not recorded"] += 1
                continue
            classes = {rcls[mode][r] for r in routes} | ({classify(direct)} if direct else set())
            if unknown_up:
                classes.add("unknown")
            if classes <= {"does not escape", "frame-bounded"}:
                hoist[mode]["candidate: every route and own reason frame-bounded"] += 1
                if not direct:
                    strict[mode] += 1
            elif "global" in classes:
                hoist[mode]["blocked: something on the way escapes globally"] += 1
            else:
                hoist[mode]["undecided: an unknown (surrender or gap) reason on the way"] += 1

    fan = Counter(len(h["objects"]) for h in hub.values())
    routed = len(obj_routes)
    shared = sum(1 for o, (routes, *_r) in obj_routes.items()
                 if any(len(hub[p]["objects"]) >= 2 for _k, p in routes))
    shared10 = sum(1 for o, (routes, *_r) in obj_routes.items()
                   if any(len(hub[p]["objects"]) >= 10 for _k, p in routes))
    exclusive = Counter()
    for o, (routes, direct, unknown_up) in obj_routes.items():
        if len(routes) == 1 and not direct and not unknown_up:
            exclusive[next(iter(routes))[1]] += 1

    def pct(x, d):
        return "%.1f %%" % (100.0 * x / d) if d else "-"

    print("== %s" % a.label)
    print("   application allocation sites %d, escaping %d (externals, not counted: %d)"
          % (len(sites), len(escaping), externals))
    for k, v in cat.most_common():
        print("      %-66s %6d  %s" % (k, v, pct(v, len(escaping))))
    print("   route counts (an object can have several): %s" % dict(route_kind))
    print("   parameters that are routes: %d; objects per parameter: %s"
          % (len(hub), ", ".join("%d:%d" % (n, c) for n, c in sorted(fan.items())[:12])))
    print("   routed sites sharing a parameter with >=1 other site: %d of %d (%s); with >=9 others: %d (%s)"
          % (shared, routed, pct(shared, routed), shared10, pct(shared10, routed)))
    pc = Counter(pcls.values())
    pw = Counter()
    for p, h in hub.items():
        pw[pcls[p]] += len(h["objects"])
    print("   why the route parameters escape, pessimistic (parameters / routed sites): %s"
          % ", ".join("%s %d / %d" % (c, pc[c], pw[c]) for c in
                      ("does not escape", "frame-bounded", "global", "unknown")))
    for mode in ("pessimistic", "optimistic"):
        rc = Counter(rcls[mode].values())
        print("   route classes, %-11s: %s" % (mode, ", ".join(
            "%s %d" % (c, rc[c]) for c in ("does not escape", "frame-bounded", "global", "unknown"))))
    print("   up-route parameters with no application caller (classed by the node alone): %d"
          % len(no_app_caller))
    for mode in ("pessimistic", "optimistic"):
        print("   -- hoisting, %s" % mode)
        for k, v in hoist[mode].most_common():
            print("      %-62s %6d  %s of escaping sites" % (k, v, pct(v, len(escaping))))
        print("      %-62s %6d  %s of escaping sites"
              % ("  of the candidates, through parameters alone (no own return/throw)",
                 strict[mode], pct(strict[mode], len(escaping))))

    print("\n   top %d parameters by allocation sites routed through them" % a.top)
    print("   %5s %5s %4s  %-15s %-22s %s" % ("sites", "excl", "mth", "class", "kinds", "parameter  <- reasons"))
    top = sorted(hub.items(), key=lambda kv: (-len(kv[1]["objects"]), kv[0]))[:a.top]
    for p, h in top:
        print("   %5d %5d %4d  %-15s %-22s %s <%d>  <- %s"
              % (len(h["objects"]), exclusive[p], len(h["methods"]), pcls[p],
                 ",".join("%s %d" % kv for kv in sorted(h["kinds"].items())),
                 p[0], p[1], ",".join(roots.get(p) or ["-"])))

    if a.json:
        out = {
            "label": a.label, "sites": len(sites), "escaping": len(escaping),
            "externals": externals, "categories": dict(cat), "routeKinds": dict(route_kind),
            "parameters": len(hub), "fanIn": {str(k): v for k, v in sorted(fan.items())},
            "routedSites": routed, "sharedSites": shared, "shared10Sites": shared10,
            "paramClass": dict(pc), "paramClassWeighted": dict(pw),
            "routeClass": {m: dict(Counter(rcls[m].values())) for m in rcls},
            "upNoAppCaller": len(no_app_caller),
            "hoist": {m: dict(hoist[m]) for m in hoist}, "hoistStrict": strict,
            "exclusiveTotal": sum(exclusive.values()),
            "categoriesOrder": list(cat),
            "top": [{"method": p[0], "param": p[1], "sites": len(h["objects"]),
                     "exclusive": exclusive[p], "methods": len(h["methods"]),
                     "class": pcls[p], "kinds": dict(h["kinds"]),
                     "reasons": roots.get(p) or []} for p, h in top],
        }
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
