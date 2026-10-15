#!/usr/bin/env python3
"""capture_level.py - how many frames up the call stack each allocation site is captured.

    python3 tools/python/capture_level.py --run-dir /tmp/rv/p6out/avrora-false \
        --class-prefix avrora. --label "avrora false" [--cap 2] [--json out.json]

A port of the prior fork's capture-level walk
(OwnershipResolverKavya2.java, object_capturing_level / resolve_escape_state) onto
upstream Stava's pre-resolution summaries. Needs a patch-0006 run: the walk reads the call
graph and each call's argument objects from <dirname>.cg.

LEVEL. For an allocation site o in method m, the level is the number of distinct callers up the
stack at which o stops being reachable from anything that outlives that frame:
  0     o can live in m's own frame (stack-allocatable)
  k     o can live in the frame k callers up, and no higher frame is needed
  heap  something on the way escapes globally, or the walk could not finish
It is the maximum over every escape state of o, and of the objects o is reached through when
the walk arrives with a field path, each state resolved as the fork resolves it:
  Escape                       heap
  NoEscape                     the current level
  <m,<returnValue,0>> on a returned object ("return a;")
                               the call results in m's callers, one level up
  <callee,<returnValue,0>> on a call result ("a = callee();")
                               the objects the callee returns, one level down
  <caller,<argument,k>>.f      the objects each caller passes as argument k, one level up
  <callee,<parameter,k>>.f     the callee's parameter k, one level down
Two methods in one call-graph SCC share a level, as in the fork.

WHAT DIFFERS FROM THE FORK, and why:
  - Context. The fork's conditional values carry a call-site bci, so a walk that went down a
    call returns up through that same call site. Upstream's carry none; the call site is found
    instead from .cg, as the sites whose argument k holds the object (or, for a value stored
    under another object, that holder), and for a call result the site at the result's bci.
    Where .cg places none, the walk falls back to every call site of that callee in the method.
  - A caller's call result is found by the call's bci in .cg, so a result that purge() already
    turned into Escape still sends the walk to heap, as the fork's explicit check does.
  - Callers. The fork asks Soot's call graph. .cg holds Spark's, and Stava falls back to CHA
    where Spark has no edge, so callers are also read from Stava's own conditional values: an
    object in c carrying <m,<returnValue,0>> or <m,<parameter,k>,[T]> makes c a caller of m.
    A return or a parameter with no caller in either goes to heap ("no caller"); the fork
    would stop there at the current level.
  - Cycles: a (method, object) already on the walk path with a prefix of the current field path
    contributes nothing, like the fork's second pass. The fork's looping fields are replaced by
    a simpler rule: a field block repeated back to back collapses to one copy. Field paths still
    longer than --max-fields go to heap.
  - The fork's getFieldObject keeps only the last object's targets; this unions them.
  - "Returned" is decided by membership in the PTG's `_ret` variable, since upstream uses one
    return conditional value for both cases.
A returned object whose callers all discard the result has no caller object to follow, so it
keeps the returning method's level, as in the fork. corpus/E05 is that case: Stava says Escape,
the walk says 0. The object is dead once returned, so the level is safe, but it disagrees with
the verdict, and the verdict cross-table shows it.

Checked by hand on corpus E01, E02, E03, E05, E06, E07, E08 and M02 (Micro-Corpus-Log Phase 17).

--cap is the fork's `currLevel > 2` cutoff. The default, 2, reproduces it; anything above the cap
is reported as "heap: above the cap". A large cap shows where those objects actually end.
"""
import argparse
import glob
import json
import os
import sys
import threading
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "extract", "python"))
from bci_to_source import parse_soot_sig  # noqa: E402
from info_to_graph import (parse_cv, parse_fields, parse_info, parse_objref,  # noqa: E402
                           split_map, split_passes, split_top, strip_outer, tarjan_scc)

HEAP = float("inf")
OBJECT_INIT = "<java.lang.Object: void <init>()>"


class Walk(Exception):
    pass


def load(run_dir):
    """-> pre summaries {m: {obj: [state]}}, fields {m: {obj: {f: set}}}, returned {m: set}."""
    pre_sum, fields, returned = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(run_dir, "*.info"))):
        pre, _post = split_passes(parse_info(path))
        for sig, b in pre.items():
            summ = {}
            for otok, stok in split_map(strip_outer(b.summary_raw, "{", "}")):
                o = parse_objref(otok)
                if o is None:
                    continue
                states = []
                for t in split_top(strip_outer(stok, "[", "]")):
                    kind, cv = parse_cv(t)
                    if kind in ("Escape", "NoEscape"):
                        states.append((kind,))
                    elif kind == "CV":
                        states.append(("CV", None if cv["method"] == "caller" else cv["method"],
                                       (cv["objType"], cv["objRef"]), tuple(cv["fieldPath"]),
                                       cv["isReal"]))
                summ[o] = states
            pre_sum[sig] = summ
            fm = defaultdict(lambda: defaultdict(set))
            for owner, f, tgt in parse_fields(b.fields_raw):
                fm[owner][f].add(tgt)
            fields[sig] = fm
            ret = set()
            for var, objs in split_map(strip_outer(b.vars_raw, "{", "}")):
                if var == "_ret":
                    for t in split_top(strip_outer(objs, "[", "]")):
                        o = parse_objref(t)
                        if o:
                            ret.add(o)
            returned[sig] = ret
    return pre_sum, fields, returned


def load_cg(path):
    """-> edges_into {callee: [(caller, bci, {k: set(obj)})]}"""
    into = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            args = {}
            if len(p) > 3 and p[3]:
                for grp in p[3].split(" "):
                    k, _, objs = grp.partition("=")
                    args[int(k)] = {parse_objref(t) for t in objs.split("|")}
            into[p[2]].append((p[0], int(p[1]), args))
    return into


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="whole-run patch-0006 output")
    ap.add_argument("--class-prefix", required=True, nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--cap", type=int, default=2, help="the fork's currLevel > 2 cutoff")
    ap.add_argument("--budget", type=int, default=10000, help="walk steps per object (fork: 10000)")
    ap.add_argument("--max-fields", type=int, default=8)
    ap.add_argument("--objects", default=None,
                    help="JSON list of [method, bci] to report separately (param_hubs --objects-out)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--show", action="store_true", help="print every site's level (small runs)")
    ap.add_argument("--sites-out", default=None,
                    help="JSON list of [method, bci, Stava verdict, level] for every site")
    a = ap.parse_args()

    name = os.path.basename(glob.glob(os.path.join(a.run_dir, "*.reasons"))[0])[:-len(".reasons")]
    pre, fields, returned = load(a.run_dir)
    into = load_cg(os.path.join(a.run_dir, name + ".cg"))

    adj = defaultdict(set)
    for callee, es in into.items():
        for caller, _b, _a in es:
            adj[caller].add(callee)
    verts = sorted(set(adj) | set(into))
    scc = tarjan_scc(verts, adj)

    def same_scc(m1, m2):
        return m1 in scc and m2 in scc and scc[m1] == scc[m2]

    kinds = {}
    ap_ = os.path.join(a.run_dir, name + ".alloc")
    if os.path.exists(ap_):
        with open(ap_, encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                kinds[(p[0], int(p[1]), p[2])] = p[3]

    def is_app(sig):
        q = parse_soot_sig(sig)
        return q is not None and any(q[0].startswith(x) for x in a.class_prefix)

    st = {}

    def fold_loops(fpath):
        """Collapse a field block repeated back to back (next.next -> next, a.b.a.b -> a.b).
        A simplified stand-in for the fork's looping fields: a chain through a recursive
        structure reaches the same kind of object again, so the repeat adds nothing."""
        p = list(fpath)
        changed = True
        while changed:
            changed = False
            for n in (1, 2, 3):
                if len(p) >= 2 * n and p[-n:] == p[-2 * n:-n]:
                    del p[-n:]
                    changed = True
                    break
        return tuple(p)

    def level(m, o, fpath, L, ctx):
        st["steps"] += 1
        if st["steps"] > a.budget:
            st["why"].add("budget")
            raise Walk()
        if L > a.cap:
            st["why"].add("above the cap")
            raise Walk()
        fpath = fold_loops(fpath)
        if len(fpath) > a.max_fields:
            st["why"].add("field path too long")
            raise Walk()
        if m == OBJECT_INIT:
            return L
        for old in st["path"].get((m, o), ()):
            if fpath[:len(old)] == old:
                return L
        summ = pre.get(m)
        if summ is None or o not in summ:
            st["why"].add("not in summary")
            st["missing"] = (m, o)
            raise Walk()
        st["path"][(m, o)].append(fpath)
        best = L
        cur, rest = {o}, list(fpath)
        while True:
            for x in cur:
                for s in summ.get(x, ()):
                    best = max(best, resolve(m, x, tuple(rest), s, L, ctx))
            if not rest:
                break
            f = rest.pop(0)
            nxt = set()
            for x in cur:
                nxt |= fields[m].get(x, {}).get(f, set())
            if not nxt:
                break
            cur = nxt
        st["path"][(m, o)].pop()
        return best

    def resolve(m, o, fpath, s, L, ctx):
        if s[0] == "Escape":
            st["why"].add("escape")
            raise Walk()
        if s[0] == "NoEscape":
            return L
        _cv, cm, (tt, tr), cvf, real = s
        extra = [()]
        holders = {o}
        if not real and tt != "returnValue":
            # not o itself but something o is stored under: find the real holder in m's PTG
            for s2 in pre[m].get(o, ()):
                if s2[0] == "CV" and s2[4] and s2[1] == cm and s2[2] == (tt, tr) \
                        and s2[3][:len(cvf)] == cvf:
                    return L
            ex, holders = set(), set()
            for oc, sts in pre[m].items():
                if any(s2[0] == "CV" and s2[4] and s2[1:4] == (cm, (tt, tr), cvf) for s2 in sts):
                    for f, tg in fields[m].get(oc, {}).items():
                        if o in tg:
                            ex.add((f,))
                            holders.add(oc)
            if not ex:
                return L
            extra = sorted(ex)
        best = L
        if tt == "returnValue" and cm == m and (o in returned.get(m, ()) or not returned.get(m)):
            # "return a;": the call results in the callers, one level up
            frames = [ctx[-1]] if ctx else callers_of(m, ret_callers.get(m, {}))
            if not frames:
                st["why"].add("no caller")
                raise Walk()
            up = ctx[:-1]
            for caller, bcis in frames:
                cs = pre.get(caller)
                if cs is None:
                    st["why"].add("not in summary")
                    st["missing"] = (caller, None)
                    raise Walk()
                if any(s2[0] == "Escape" for b in (bcis or ())
                       for s2 in cs.get(("external", b), ())):
                    st["why"].add("escape")
                    raise Walk()
                nl = L if same_scc(m, caller) else L + 1
                for x, sts in cs.items():
                    for s2 in sts:
                        if s2[0] == "CV" and s2[1] == m and s2[2][0] == "returnValue" \
                                and cvf[:len(s2[3])] == s2[3]:
                            for ex in extra:
                                best = max(best, level(caller, x, cvf[len(s2[3]):] + ex + fpath,
                                                       nl, up))
        elif tt == "returnValue":
            # "a = callee();": the objects the callee returns, one level down
            if cm not in pre:
                st["why"].add("not in summary")
                st["missing"] = (cm, None)
                raise Walk()
            nl = L if same_scc(m, cm) else L - 1
            here = call_sites(m, cm, None, {o} if o[0] == "external" else set(), o)
            rets = returned.get(cm, ())
            for x, sts in pre[cm].items():
                if rets and x not in rets:
                    continue
                for s2 in sts:
                    if s2[0] == "CV" and s2[1] == cm and s2[2][0] == "returnValue" \
                            and cvf[:len(s2[3])] == s2[3]:
                        for ex in extra:
                            best = max(best, level(cm, x, cvf[len(s2[3]):] + ex + fpath, nl,
                                                   ctx + (here,)))
        elif tt == "argument":
            # <caller,<argument,k>>: each caller's argument k, one level up
            byc = arg_callers.get((m, tr), {})
            frames = [ctx[-1]] if ctx else callers_of(m, byc)
            if not frames:
                st["why"].add("no caller")
                raise Walk()
            up = ctx[:-1]
            for caller, bcis in frames:
                if caller not in pre:
                    st["why"].add("not in summary")
                    st["missing"] = (caller, None)
                    raise Walk()
                nl = L if same_scc(m, caller) else L + 1
                objs = set()
                for b, args in calls_from.get((caller, m), ()):
                    if bcis is not None and b in bcis:
                        objs |= args.get(tr, set())
                if not objs:
                    # .cg places no call, or binds nothing to argument k there: take the objects
                    # Stava itself recorded as passed to m as argument k in this caller
                    objs = byc.get(caller, set())
                for x in sorted(objs):
                    for ex in extra:
                        best = max(best, level(caller, x, cvf + ex + fpath, nl, up))
        elif tt == "parameter":
            # <callee,<parameter,k>>: o is passed down, one level down
            if cm == OBJECT_INIT:
                return L                        # the fork's special case, before any lookup
            if cm not in pre:
                st["why"].add("not in summary")
                st["missing"] = (cm, None)
                raise Walk()
            nl = L if same_scc(m, cm) else L - 1
            here = call_sites(m, cm, tr, holders, None)
            for ex in extra:
                best = max(best, level(cm, ("parameter", tr), cvf + ex + fpath, nl, ctx + (here,)))
        else:
            st["why"].add("unexpected conditional value %s" % tt)
            raise Walk()
        return best

    calls_from = defaultdict(list)
    for callee, es in into.items():
        for caller, bci, args in es:
            calls_from[(caller, callee)].append((bci, args))

    # Stava's own record of who calls whom, from the conditional values: an object in c with
    # <m,<returnValue,0>> is a call result of m in c; one with <m,<parameter,k>,[T]> is passed to
    # m as argument k in c. It covers the calls Spark's graph lacks: Stava falls back to CHA, and
    # a method Spark never reached has no .cg edge in at all.
    ret_callers = defaultdict(lambda: defaultdict(set))
    arg_callers = defaultdict(lambda: defaultdict(set))
    for c, summ in pre.items():
        for x, sts in summ.items():
            for s2 in sts:
                if s2[0] != "CV" or s2[1] is None:
                    continue
                if s2[2][0] == "returnValue" and (s2[1] != c or x not in returned.get(c, ())):
                    ret_callers[s2[1]][c].add(x)
                elif s2[2][0] == "parameter" and s2[4]:
                    arg_callers[(s2[1], s2[2][1])][c].add(x)

    def callers_of(m, by_caller):
        """Every caller of m as a context frame (caller, bcis): the .cg call sites, plus callers
        only Stava's conditional values name, with bcis None (every call in that caller)."""
        frames = {}
        for caller, bci, _args in into.get(m, ()):
            frames.setdefault(caller, set()).add(bci)
        out = [(c, frozenset(b)) for c, b in sorted(frames.items())]
        out += [(c, None) for c in sorted(by_caller) if c not in frames]
        return out

    def call_sites(m, cm, k, holders, result):
        """The context frame this step goes down through: (m, the call sites of cm in m that
        pass one of `holders` as argument k, or for a call result the site at its own bci).
        (m, every .cg site of cm in m) when none matches, and (m, None) when .cg has none."""
        sites = calls_from.get((m, cm), ())
        if result is not None:
            hit = [b for b, _a in sites if result[0] == "external" and b == result[1]]
        else:
            hit = [b for b, args in sites if args.get(k, set()) & holders]
        if not hit:
            hit = [b for b, _a in sites]
        return (m, frozenset(hit) if hit else None)

    missing = Counter()

    def capture(m, o):
        st.clear()
        st.update(steps=0, why=set(), path=defaultdict(list))
        try:
            return level(m, o, (), 0, ()), set()
        except Walk:
            if "missing" in st:
                missing[st["missing"][0]] += 1
            return HEAP, set(st["why"])

    targets = sorted((m, o) for m, summ in pre.items() if is_app(m)
                     for o in summ if o[0] == "internal")
    if kinds:
        targets = [t for t in targets if kinds.get((t[0], t[1][1], "internal")) == "NEW"]
    res = {}
    for m, o in targets:
        res[(m, o[1])] = capture(m, o)

    def bucket(lv, why):
        if lv != HEAP:
            return str(int(lv))
        order = ("escape", "no caller", "not in summary", "above the cap", "budget",
                 "field path too long")
        for w in order:
            if w in why:
                return "heap: " + w
        return "heap: " + ",".join(sorted(why))

    hist = Counter(bucket(*v) for v in res.values())
    neg = sum(1 for lv, _w in res.values() if lv != HEAP and lv < 0)

    # cross-check against Stava's own verdict (resolved .info, via .res-equivalent statuses)
    verdict = {}
    for path in sorted(glob.glob(os.path.join(a.run_dir, "*.info"))):
        _pre, post = split_passes(parse_info(path))
        for sig, b in post.items():
            if not is_app(sig):
                continue
            for otok, stok in split_map(strip_outer(b.summary_raw, "{", "}")):
                o = parse_objref(otok)
                if o and o[0] == "internal":
                    verdict[(sig, o[1])] = "NoEscape" if "NoEscape" in stok else "Escape"
    cross = Counter((verdict.get(k, "?"), "0" if v[0] == 0 else ("heap" if v[0] == HEAP else ">0"))
                    for k, v in res.items())

    def show(title, keys):
        n = len(keys)
        h = Counter(bucket(*res[k]) for k in keys)
        print("   %s: %d allocation sites" % (title, n))
        for b in sorted(h, key=lambda s: (s.startswith("heap"), s if s.startswith("heap")
                                          else int(s))):
            print("      level %-26s %6d  %5.1f %%" % (b, h[b], 100.0 * h[b] / max(1, n)))
        return h

    print("== %s  (cap %d, budget %d, SCCs over %d methods in .cg)"
          % (a.label, a.cap, a.budget, len(scc)))
    allh = show("all application allocation sites (.alloc NEW)" if kinds
                else "all application internal nodes", list(res))
    print("   levels below 0 (only callees below the site bound it): %d" % neg)
    print("   Stava verdict x walk: %s" % dict(sorted(cross.items())))
    if missing:
        print("   methods with no summary that ended a walk (top 8): %s" % missing.most_common(8))
    if a.sites_out:
        with open(a.sites_out, "w", encoding="utf-8") as fh:
            json.dump([[k[0], k[1], verdict.get(k, "?"), bucket(*res[k])] for k in sorted(res)],
                      fh, indent=0)
    if a.show:
        for k in sorted(res):
            print("      %-8s %-12s %s:%d" % (verdict.get(k, "?"), bucket(*res[k]), k[0], k[1]))
    subsets = {}
    if a.objects:
        with open(a.objects, encoding="utf-8") as fh:
            want = json.load(fh)
        for title, lst in want.items():
            keys = [(m, int(b)) for m, b in lst if (m, int(b)) in res]
            subsets[title] = dict(show(title, keys))
            missing = len(lst) - len(keys)
            if missing:
                print("      (%d of the listed objects are not allocation sites in this run)" % missing)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"label": a.label, "cap": a.cap, "budget": a.budget,
                       "sites": len(res), "levels": dict(allh), "belowZero": neg,
                       "cross": {"%s/%s" % k: v for k, v in cross.items()},
                       "subsets": subsets}, fh, indent=2)


if __name__ == "__main__":
    sys.setrecursionlimit(200000)
    threading.stack_size(512 * 1024 * 1024)
    t = threading.Thread(target=main)
    t.start()
    t.join()
