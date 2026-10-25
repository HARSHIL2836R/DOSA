#!/usr/bin/env python3
"""alloc_weight.py - the static ownership classes, weighted by what each site allocates at run time.

    python3 tools/python/ownership/dyn/alloc_weight.py --bench avrora [--json out.json]

WEIGHT. Flight Recorder's allocation events are samples: an InNewTLAB event means the allocation
at its top frame needed a new thread-local buffer, and stands for that buffer's size in bytes; an
OutsideTLAB event stands for its own allocation. Summing tlabSize (or allocationSize) per
(method, bci) estimates the bytes each site allocates, the usual reading of these events.
Allocations HotSpot's C2 removed by scalar replacement never allocate and are not sampled.

JOIN. The top frame's method and bytecode index against the (method, bci) of the static
analysis (build/own/bench/<bench>/<name>[-id].own) and against Phase 17's application sites
(build/out/capture-level/<bench>-false-cap50.sites.json: Stava's verdict and the fork's walk).

REPORTED, as shares of the sampled bytes:
    at an application site of the benchmark's packages, and of those
    OWN / UP / HEAP / not in Spark, with and without identity returns
    Stava NoEscape, and the fork's walk level 0 / 1-2 / heap
"""
import argparse
import collections
import json
import os
import re
import sys

H = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
BASE = {"avrora": "dacapo", "xalan": "xalan", "luindex": "luindex", "fop": "fop", "h2": "h2", "pmd": "pmd"}
PRIM = {"B": "byte", "C": "char", "D": "double", "F": "float", "I": "int", "J": "long", "S": "short",
        "Z": "boolean", "V": "void"}


def jtype(d, i):
    dims = 0
    while d[i] == "[":
        dims += 1
        i += 1
    if d[i] == "L":
        j = d.index(";", i)
        t = d[i + 1:j].replace("/", ".")
        i = j + 1
    else:
        t = PRIM[d[i]]
        i += 1
    return t + "[]" * dims, i


def soot_sig(cls, name, desc):
    params, i = [], 1
    while desc[i] != ")":
        t, i = jtype(desc, i)
        params.append(t)
    ret, _ = jtype(desc, i + 1)
    return "<%s: %s %s(%s)>" % (cls.replace("/", "."), ret, name, ",".join(params))


def type_name(t):
    if isinstance(t, dict):
        return t.get("name") or t.get("javaName") or "?"
    return str(t)


JDK_PREFIXES = ("java.", "javax.", "sun.", "com.sun.", "jdk.")


def read_events(path, stacks=None):
    """alloc.tsv from AllocWeights.java: type, name, descriptor, bci, bytes, events[, below].
    If `stacks` is a list, each row's (weight, [(sig, bci), ...] top first) is appended to it."""
    weights = collections.Counter()
    events = total = 0
    for line in open(path, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if line.startswith("#"):
            continue
        w, n = int(c[4]), int(c[5])
        total += w
        events += n
        key = ("?", -1) if c[0] == "?" else (soot_sig(c[0], c[1], c[2]), int(c[3]))
        weights[key] += w
        if stacks is not None and key[0] != "?":
            frames = [key]
            if len(c) > 6 and c[6]:
                for f in c[6].split(" < "):
                    t, nm, rest = f.split(";", 2)        # descriptors contain ';' themselves
                    d, b = rest.rsplit(";", 1)
                    frames.append((soot_sig(t, nm, d), int(b)))
            stacks.append((w, frames))
    return weights, events, total


def is_jdk_sig(sig):
    return sig[1:].startswith(JDK_PREFIXES)


def inlined_key(frames, depth=3):
    """The (method, bci) key library inlining gives the allocation at frames[0], if the first
    non-JDK frame is within `depth` frames below it; None otherwise."""
    for k, (sig, _b) in enumerate(frames):
        if not is_jdk_sig(sig):
            break
    else:
        return None
    if k == 0 or k > depth:
        return None
    chain = "".join("%d>%s@" % (frames[i][1], frames[i - 1][0]) for i in range(k, 0, -1))
    return (frames[k][0] + "#" + chain, frames[0][1])


def read_own(path):
    out = {}
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        parts = c[0].rsplit("|", 2)
        if len(parts) != 3:          # Spark's placeholders (@NOUNIT:...) name no bci
            continue
        out[(parts[0], int(parts[1]))] = (c[2], c[6] == "1")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--top", type=int, default=0, help="list the N heaviest sites")
    ap.add_argument("--inline-dir", default=None,
                    help="directory of a library-inlining run (default build/own/inline/<bench>)")
    ap.add_argument("--brief", action="store_true",
                    help="one line: the figures of Micro-Corpus-Log F20.5 and F21.6")
    a = ap.parse_args()
    b = a.bench
    out = sys.stdout
    if a.brief:
        sys.stdout = open(os.devnull, "w")
    stacks = []
    weights, events, total = read_events(os.path.join(H, "build", "own", "dyn", b, "alloc.tsv"), stacks)
    sites = json.load(open(os.path.join(H, "build", "out", "capture-level", "%s-false-cap50.sites.json" % b)))
    pop = {(m, bci): (verdict, walk) for m, bci, verdict, walk in sites}
    app_w = sum(w for k, w in weights.items() if k in pop)
    print("== %s: %d allocation events, %.1f MB sampled; %.1f %% at the %d application sites of Phase 17"
          " (%d of them sampled)" % (b, events, total / 2**20, 100.0 * app_w / max(1, total), len(pop),
                                     sum(1 for k in weights if k in pop)))
    res = {"bench": b, "events": events, "bytes": total, "app_bytes": app_w}
    vw = collections.Counter()
    ww = collections.Counter()
    for k, w in weights.items():
        if k in pop:
            verdict, walk = pop[k]
            vw[verdict] += w
            ww["heap" if walk.startswith("heap") else ("0" if walk == "0" else "1-2" if walk in ("1", "2") else "3+")] += w
    print("   Stava verdict, share of application bytes: %s" % {
        k: "%.1f %%" % (100.0 * v / max(1, app_w)) for k, v in sorted(vw.items())})
    print("   fork's walk level:                         %s" % {
        k: "%.1f %%" % (100.0 * v / max(1, app_w)) for k, v in sorted(ww.items())})
    res["stava"] = dict(vw)
    res["walk"] = dict(ww)
    for tag, suffix in (("B", ""), ("B+id", "-id")):
        own = read_own(os.path.join(H, "build", "own", "bench", b, BASE[b] + suffix + ".own"))
        if own is None:
            print("   %s: no .own yet" % tag)
            continue
        cw = collections.Counter()
        allw = collections.Counter()
        for k, w in weights.items():
            o = own.get(k)
            if o is None:
                c = "no stack" if k[0] == "?" else "not in Spark"
            else:
                cls, rec = o
                c = cls + (" (recursive)" if rec and cls in ("OWN", "UP") else "")
            allw[c] += w
            if k in pop:
                cw[c] += w
        print("   ownership %-5s share of application bytes: %s" % (tag, {
            k: "%.1f %%" % (100.0 * v / max(1, app_w)) for k, v in sorted(cw.items())}))
        print("   ownership %-5s share of all sampled bytes: %s" % (tag, {
            k: "%.1f %%" % (100.0 * v / max(1, total)) for k, v in sorted(allw.items())}))
        res[tag] = dict(cw)
        res[tag + " all"] = dict(allw)
    # library inlining (Phase 21): every sampled byte, a library allocation classified through the
    # copy inlined into its application caller when the call chain matches one
    inl = read_own(os.path.join(a.inline_dir or os.path.join(H, "build", "own", "inline", b),
                                BASE[b] + "-id-inl.own"))
    if inl is not None:
        cw, via = collections.Counter(), collections.Counter()
        lib_total = 0
        for w, frames in stacks:
            k = inlined_key(frames)
            o = inl.get(k) if k else None
            if o is not None:
                via[o[0]] += w
            else:
                o = inl.get(frames[0])
            c = "not in Spark" if o is None else o[0] + (" (recursive)" if o[1] and o[0] in ("OWN", "UP") else "")
            cw[c] += w
            if is_jdk_sig(frames[0][0]):
                lib_total += w
        print("   ownership B+id+inl share of all sampled bytes: %s" % {
            k: "%.1f %%" % (100.0 * v / max(1, total)) for k, v in sorted(cw.items())})
        print("      classified through an inlined copy: %.1f %% of all bytes (%s); library allocations are %.1f %%"
              % (100.0 * sum(via.values()) / max(1, total),
                 {k: "%.1f %%" % (100.0 * v / max(1, total)) for k, v in sorted(via.items())},
                 100.0 * lib_total / max(1, total)))
        res["B+id+inl all"] = dict(cw)
        res["inlined"] = dict(via)
    if a.top:
        own = read_own(os.path.join(H, "build", "own", "bench", b, BASE[b] + "-id.own")) or {}
        why = {}
        wp = os.path.join(H, "build", "own", "bench", b, BASE[b] + "-id.ownwhy")
        if os.path.exists(wp):
            for line in open(wp, encoding="utf-8"):
                c = line.rstrip("\n").split("\t")
                parts = c[0].rsplit("|", 2)
                if line.startswith("#") or len(parts) != 3:
                    continue
                why[(parts[0], int(parts[1]))] = "%s %s via %s" % (c[1], c[2][:70], c[3][:60])
        print("   heaviest sites (share of all sampled bytes; B+id class; Stava; why HEAP):")
        for k, w in weights.most_common(a.top):
            o = own.get(k)
            v = pop.get(k)
            print("   %5.1f %%  %-4s %-8s %-9s %s:%d  %s" % (
                100.0 * w / max(1, total), "app" if v else "", o[0] if o else "-", v[0] if v else "",
                k[0][:90], k[1], why.get(k, "")))
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8", newline="\n"), indent=1)
    if a.brief:
        sys.stdout = out

        def framed(d, denom):
            return 100.0 * sum(v for k, v in d.items() if k.startswith(("OWN", "UP"))) / max(1, denom)

        via = res.get("inlined", {})
        print("%-8s application bytes %4.1f %% of all | of them: Stava NoEscape %4.1f %%, walk level 0 %4.1f %%,"
              " OWN+UP %4.1f %% | all bytes OWN+UP: %4.1f %% -> %4.1f %% with inlining"
              " (through a copy %4.1f %%, of it OWN/UP %4.1f %%) | application bytes not in Spark %4.1f %%"
              % (b, 100.0 * app_w / max(1, total), 100.0 * vw.get("NoEscape", 0) / max(1, app_w),
                 100.0 * ww.get("0", 0) / max(1, app_w), framed(res.get("B+id", {}), app_w),
                 framed(res.get("B+id all", {}), total), framed(res.get("B+id+inl all", {}), total),
                 100.0 * sum(via.values()) / max(1, total), framed(via, total),
                 100.0 * res.get("B+id", {}).get("not in Spark", 0) / max(1, app_w)))


if __name__ == "__main__":
    main()
