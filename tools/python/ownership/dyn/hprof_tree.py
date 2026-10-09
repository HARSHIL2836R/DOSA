#!/usr/bin/env python3
"""hprof_tree.py - the ownership tree of one heap dump (design note 2026-09-24-Ownership-Trees.md,
§1 and D0 of §6.2).

    python3 tools/python/ownership/dyn/hprof_tree.py dump.hprof [--show Box Item] [--json out.json]

GRAPH (§1.1, from the HPROF records):
    ROOT -> GLOBAL
    ROOT -> thread t -> frame[deepest] -> ... -> frame[0]        one chain per thread; frame
                                                                 numbers are HPROF's depth, 0 =
                                                                 the running method
    frame -> o      for ROOT JAVA FRAME and ROOT JNI LOCAL records naming that thread and depth
    GLOBAL -> o     every other root (sticky class, JNI global, thread object, monitor, native
                    stack, thread block, unknown), and every class object
    class -> o      static fields
    o -> p          instance fields and object-array elements

The dump is taken with live=true, so every object in it was reachable at a safepoint. Which
locals HotSpot reports for a frame is its business: a compiled frame reports its oop map (live
locals), an interpreted frame may report a dead one, and that overstates frame ownership.

OUTPUT: for every object, its region (the nearest frame above it in the dominator tree, or
GLOBAL) and whether its immediate owner is a frame, an object or GLOBAL; counts and shallow
bytes by region, by frame depth and method, and the subtree sizes under GLOBAL.
"""
import argparse
import collections
import json
import struct
import sys
from array import array

BASIC = {2: 0, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}   # 2 = object: id size


class Dump:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.b = f.read()
        b = self.b
        end = b.index(b"\0")
        self.version = b[:end].decode()
        self.ids, = struct.unpack_from(">I", b, end + 1)
        self.idf = ">Q" if self.ids == 8 else ">I"
        BASIC[2] = self.ids
        self.strings = {}
        self.class_name = {}            # class object id -> name
        self.frames = {}                # frame id -> (method, class serial)
        self.class_serial_name = {}     # class serial -> name
        self.traces = {}                # trace serial -> (thread serial, [frame ids])
        self.thread_trace = {}          # thread serial -> trace serial
        self.thread_obj = {}            # thread serial -> thread object id
        self.frame_roots = []           # (object id, thread serial, depth)
        self.global_roots = []          # object ids
        self.classes = {}               # class id -> (super id, [(name id, type)], statics [(type, value)], inst size)
        self.instances = []             # (id, class id, offset, length)
        self.objarrays = []             # (id, class id, offset, count)
        self.primarrays = []            # (id, elem type, count)
        self.parse(end + 1 + 4 + 8)

    def rid(self, o):
        return struct.unpack_from(self.idf, self.b, o)[0]

    def parse(self, p):
        b, ids = self.b, self.ids
        n = len(b)
        while p < n:
            tag = b[p]
            length, = struct.unpack_from(">I", b, p + 5)
            body = p + 9
            if tag == 0x01:
                self.strings[self.rid(body)] = b[body + ids:body + length].decode("utf-8", "replace")
            elif tag == 0x02:
                serial, = struct.unpack_from(">I", b, body)
                cid = self.rid(body + 4)
                nid = self.rid(body + 8 + ids)
                self.class_name[cid] = nid
                self.class_serial_name[serial] = nid
            elif tag == 0x04:
                fid = self.rid(body)
                mname = self.rid(body + ids)
                cser, = struct.unpack_from(">I", b, body + 4 * ids)
                self.frames[fid] = (mname, cser)
            elif tag == 0x05:
                tser, thr, nfr = struct.unpack_from(">III", b, body)
                self.traces[tser] = (thr, [self.rid(body + 12 + k * ids) for k in range(nfr)])
            elif tag in (0x0C, 0x1C):
                self.heap(body, body + length)
            p = body + length
        # resolve names now that every string is known
        self.class_name = {k: self.strings.get(v, "?").replace("/", ".") for k, v in self.class_name.items()}
        self.class_serial_name = {k: self.strings.get(v, "?").replace("/", ".") for k, v in self.class_serial_name.items()}

    def heap(self, p, end):
        b, ids = self.b, self.ids
        u4 = struct.Struct(">I").unpack_from
        while p < end:
            t = b[p]
            p += 1
            if t == 0xFF:
                self.global_roots.append(self.rid(p)); p += ids
            elif t == 0x01:
                self.global_roots.append(self.rid(p)); p += 2 * ids
            elif t in (0x02, 0x03):
                o = self.rid(p)
                thr, depth = struct.unpack_from(">II", b, p + ids)
                self.frame_roots.append((o, thr, depth)); p += ids + 8
            elif t in (0x04, 0x06):
                self.global_roots.append(self.rid(p)); p += ids + 4
            elif t in (0x05, 0x07):
                self.global_roots.append(self.rid(p)); p += ids
            elif t == 0x08:
                o = self.rid(p)
                thr, tser = struct.unpack_from(">II", b, p + ids)
                self.thread_obj[thr] = o
                self.thread_trace[thr] = tser
                self.global_roots.append(o); p += ids + 8
            elif t == 0x20:
                cid = self.rid(p)
                sup = self.rid(p + ids + 4)
                q = p + 7 * ids + 4
                isize, = u4(b, q); q += 4
                ncp, = struct.unpack_from(">H", b, q); q += 2
                for _ in range(ncp):
                    ty = b[q + 2]; q += 3 + BASIC[ty]
                nst, = struct.unpack_from(">H", b, q); q += 2
                statics = []
                for _ in range(nst):
                    ty = b[q + ids]
                    if ty == 2:
                        statics.append(self.rid(q + ids + 1))
                    q += ids + 1 + BASIC[ty]
                nif, = struct.unpack_from(">H", b, q); q += 2
                fields = []
                for _ in range(nif):
                    fields.append((self.rid(q), b[q + ids])); q += ids + 1
                self.classes[cid] = (sup, fields, statics, isize)
                p = q
            elif t == 0x21:
                o = self.rid(p)
                cid = self.rid(p + ids + 4)
                nb, = u4(b, p + 2 * ids + 4)
                self.instances.append((o, cid, p + 2 * ids + 8, nb))
                p += 2 * ids + 8 + nb
            elif t == 0x22:
                o = self.rid(p)
                cnt, = u4(b, p + ids + 4)
                cid = self.rid(p + ids + 8)
                self.objarrays.append((o, cid, p + 2 * ids + 8, cnt))
                p += 2 * ids + 8 + cnt * ids
            elif t == 0x23:
                o = self.rid(p)
                cnt, = u4(b, p + ids + 4)
                ety = b[p + ids + 8]
                self.primarrays.append((o, ety, cnt))
                p += ids + 9 + cnt * BASIC[ety]
            else:
                raise ValueError("unknown heap sub-record 0x%02x at %d" % (t, p - 1))

    def ref_offsets(self, cid, cache={}):
        """Byte offsets of reference fields in an instance of cid: this class, then its supers."""
        r = cache.get(cid)
        if r is not None:
            return r
        offs, off, c = [], 0, cid
        while c and c in self.classes:
            sup, fields, _, _ = self.classes[c]
            for _name, ty in fields:
                if ty == 2:
                    offs.append(off)
                off += BASIC[ty]
            c = sup
        cache[cid] = offs
        return offs


def dominators(n, off, adj):
    """Cooper, Harvey, Kennedy. Node 0 is the root. -1 = unreachable."""
    po = array("i", [-1]) * n
    order = array("i")
    seen = bytearray(n)
    stack = [(0, off[0])]
    seen[0] = 1
    while stack:
        v, i = stack[-1]
        if i < off[v + 1]:
            stack[-1] = (v, i + 1)
            w = adj[i]
            if not seen[w]:
                seen[w] = 1
                stack.append((w, off[w]))
        else:
            stack.pop()
            po[v] = len(order)
            order.append(v)
    preds = [[] for _ in range(n)]
    for v in order:
        for i in range(off[v], off[v + 1]):
            preds[adj[i]].append(v)
    idom = array("i", [-1]) * n
    idom[0] = 0
    changed = True
    while changed:
        changed = False
        for k in range(len(order) - 1, -1, -1):
            bnode = order[k]
            if bnode == 0:
                continue
            nd = -1
            for p in preds[bnode]:
                if idom[p] == -1:
                    continue
                if nd == -1:
                    nd = p
                    continue
                f1, f2 = p, nd
                while f1 != f2:
                    while po[f1] < po[f2]:
                        f1 = idom[f1]
                    while po[f2] < po[f1]:
                        f2 = idom[f2]
                nd = f1
            if idom[bnode] != nd:
                idom[bnode] = nd
                changed = True
    return idom


def dominators_lt(n, off, adj, root=0):
    """Lengauer-Tarjan with path compression (the simple version), iterative. The Cooper,
    Harvey, Kennedy iteration above walks dominator chains, which a heap with long linked
    structures makes deep: fop's first dump ran for over 15 minutes. -1 = unreachable."""
    semi = array("i", [-1]) * n
    parent = array("i", [-1]) * n
    vertex = array("i")
    semi[root] = 0
    vertex.append(root)
    stack = [(root, off[root])]
    while stack:
        v, i = stack[-1]
        if i < off[v + 1]:
            stack[-1] = (v, i + 1)
            w = adj[i]
            if semi[w] == -1:
                parent[w] = v
                semi[w] = len(vertex)
                vertex.append(w)
                stack.append((w, off[w]))
        else:
            stack.pop()
    preds = [[] for _ in range(n)]
    for v in vertex:
        for i in range(off[v], off[v + 1]):
            preds[adj[i]].append(v)
    ancestor = array("i", [-1]) * n
    label = array("i", range(n))
    idom = array("i", [-1]) * n
    bucket = {}

    def evaluate(v):
        if ancestor[v] == -1:
            return v
        path = []
        u = v
        while ancestor[ancestor[u]] != -1:
            path.append(u)
            u = ancestor[u]
        for x in reversed(path):
            a = ancestor[x]
            if semi[label[a]] < semi[label[x]]:
                label[x] = label[a]
            ancestor[x] = ancestor[a]
        return label[v]

    for k in range(len(vertex) - 1, 0, -1):
        w = vertex[k]
        for v in preds[w]:
            u = evaluate(v)
            if semi[u] < semi[w]:
                semi[w] = semi[u]
        bucket.setdefault(vertex[semi[w]], []).append(w)
        p = parent[w]
        ancestor[w] = p
        for v in bucket.pop(p, ()):
            u = evaluate(v)
            idom[v] = u if semi[u] < semi[v] else p
    for k in range(1, len(vertex)):
        w = vertex[k]
        if idom[w] != vertex[semi[w]]:
            idom[w] = idom[idom[w]]
    idom[root] = root
    return idom


def build(d):
    """Nodes: 0 ROOT, 1 GLOBAL, thread and frame nodes, then objects. Returns graph and labels."""
    labels = ["ROOT", "GLOBAL"]
    kind = ["root", "global"]           # per node: root, global, thread, frame, object
    frame_of = {}                       # (thread serial, depth) -> node
    edges_s, edges_d = array("i"), array("i")

    def edge(s, t):
        edges_s.append(s); edges_d.append(t)

    edge(0, 1)
    threads = sorted(set(d.thread_trace) | {t for _, t, _ in d.frame_roots})
    frame_depth, frame_method = {}, {}
    for t in threads:
        tn = len(labels)
        labels.append("thread %d" % t); kind.append("thread")
        edge(0, tn)
        tr = d.traces.get(d.thread_trace.get(t), (t, []))[1]
        maxd = max([len(tr) - 1] + [dep for _, th, dep in d.frame_roots if th == t])
        prev = tn
        for dep in range(maxd, -1, -1):
            fn = len(labels)
            meth = "?"
            if dep < len(tr) and tr[dep] in d.frames:
                mname, cser = d.frames[tr[dep]]
                meth = d.class_serial_name.get(cser, "?") + "." + d.strings.get(mname, "?")
            labels.append("frame t%d d%d %s" % (t, dep, meth)); kind.append("frame")
            frame_of[(t, dep)] = fn
            frame_depth[fn] = dep
            frame_method[fn] = meth
            edge(prev, fn)
            prev = fn
    base = len(labels)
    oid = {}
    objs = []                            # (id, class name, shallow bytes)
    for o, cid, _, nb in d.instances:
        oid[o] = len(objs); objs.append((o, d.class_name.get(cid, "?"), d.classes.get(cid, (0, 0, 0, nb + 16))[3] or nb + 16))
    for o, cid, _, cnt in d.objarrays:
        oid[o] = len(objs); objs.append((o, d.class_name.get(cid, "?[]"), 16 + cnt * 4))
    for o, ety, cnt in d.primarrays:
        oid[o] = len(objs); objs.append((o, "prim[%d]" % ety, 16 + cnt * BASIC[ety]))
    for cid in d.classes:
        if cid not in oid:
            oid[cid] = len(objs); objs.append((cid, "class " + d.class_name.get(cid, "?"), 0))
    n = base + len(objs)

    def node(o):
        i = oid.get(o)
        return None if i is None else base + i

    for o, t, dep in d.frame_roots:
        x = node(o)
        if x is not None:
            edge(frame_of[(t, dep)], x)
    for o in d.global_roots:
        x = node(o)
        if x is not None:
            edge(1, x)
    for cid, (_sup, _f, statics, _s) in d.classes.items():
        c = node(cid)
        edge(1, c)
        for v in statics:
            x = node(v)
            if x is not None:
                edge(c, x)
    rid, b, ids = d.rid, d.b, d.ids
    for o, cid, off0, _nb in d.instances:
        s = node(o)
        for off in d.ref_offsets(cid):
            x = node(rid(off0 + off))
            if x is not None:
                edge(s, x)
    for o, _cid, off0, cnt in d.objarrays:
        s = node(o)
        for k in range(cnt):
            x = node(rid(off0 + k * ids))
            if x is not None:
                edge(s, x)
    # CSR
    off = array("i", [0]) * (n + 1)
    for s in edges_s:
        off[s + 1] += 1
    for i in range(n):
        off[i + 1] += off[i]
    adj = array("i", [0]) * len(edges_s)
    pos = array("i", off[:n])
    for s, t in zip(edges_s, edges_d):
        adj[pos[s]] = t
        pos[s] += 1
    return n, off, adj, labels, kind, base, objs, frame_depth, frame_method


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hprof")
    ap.add_argument("--show", nargs="*", default=[], help="print the owner chain of objects of these classes")
    ap.add_argument("--json", default=None)
    ap.add_argument("--check-chk", action="store_true",
                    help="also run Cooper-Harvey-Kennedy and compare (small dumps only)")
    a = ap.parse_args()
    d = Dump(a.hprof)
    n, off, adj, labels, kind, base, objs, fdepth, fmeth = build(d)
    idom = dominators_lt(n, off, adj)
    if a.check_chk:
        other = dominators(n, off, adj)
        diff = sum(1 for v in range(n) if idom[v] != other[v])
        print("check: Lengauer-Tarjan and Cooper-Harvey-Kennedy differ on %d of %d nodes" % (diff, n))

    def name(v):
        return labels[v] if v < base else "%s#%x" % (objs[v - base][1], objs[v - base][0])

    region_count = collections.Counter()
    region_bytes = collections.Counter()
    owner_kind = collections.Counter()
    depth_count = collections.Counter()
    method_count = collections.Counter()
    subtree = collections.Counter()      # object directly under GLOBAL/ROOT -> subtree size
    region_classes = {"frame": collections.Counter(), "global": collections.Counter()}
    unreached = 0
    for i, (o, cls, sz) in enumerate(objs):
        v = base + i
        if idom[v] == -1:
            unreached += 1
            continue
        x = idom[v]
        ok = kind[x] if x < base else "object"
        while x >= base:
            x = idom[x]
        reg = kind[x] if kind[x] == "frame" else "global"
        region_count[reg] += 1
        region_bytes[reg] += sz
        owner_kind[(reg, ok)] += 1
        region_classes[reg][cls] += 1
        if reg == "frame":
            depth_count[fdepth[x]] += 1
            method_count[fmeth[x]] += 1
        else:
            # the top of this object's subtree under GLOBAL
            y = v
            while idom[y] >= base:
                y = idom[y]
            subtree[y] += 1
        if a.show and cls.split(".")[-1] in a.show:
            chain = [name(v)]
            y = v
            while y != 0:
                y = idom[y]
                chain.append(name(y))
            print("   " + " <- ".join(chain))
    tot = sum(region_count.values())
    print("%s: %d objects reachable (%d unreachable in the dump), %d threads" % (
        a.hprof, tot, unreached, sum(1 for k in kind if k == "thread")))
    for reg in ("frame", "global"):
        print("   %-7s %9d objects %5.1f %%  %11d bytes %5.1f %%" % (
            reg, region_count[reg], 100.0 * region_count[reg] / max(1, tot), region_bytes[reg],
            100.0 * region_bytes[reg] / max(1, sum(region_bytes.values()))))
    print("   immediate owner: %s" % dict(sorted(owner_kind.items())))
    print("   frame-owned by depth (0 = running method): %s" % dict(sorted(depth_count.items())[:12]))
    print("   top frame methods: %s" % method_count.most_common(8))
    sizes = collections.Counter()
    for top, s in subtree.items():
        sizes["1" if s == 1 else "2-4" if s <= 4 else "5-16" if s <= 16 else "17-256" if s <= 256 else "257+"] += s
    print("   objects under GLOBAL, by the size of the subtree they sit in: %s" % dict(sizes))
    for reg in ("frame", "global"):
        print("   top classes under %s: %s" % (reg, region_classes[reg].most_common(6)))
    if a.json:
        json.dump({"dump": a.hprof, "objects": tot, "region_count": region_count,
                   "region_bytes": region_bytes,
                   "owner_kind": {"%s|%s" % k: v for k, v in owner_kind.items()},
                   "depth": depth_count, "subtree_sizes": sizes},
                  open(a.json, "w", encoding="utf-8", newline="\n"), indent=1)


if __name__ == "__main__":
    main()
