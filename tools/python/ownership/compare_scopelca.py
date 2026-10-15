#!/usr/bin/env python3
"""compare_scopelca.py - compare benchmark ownership stats before and after Scope LCA."""
import os
import json
import collections

H = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BENCH = [
    ("avrora", "dacapo", ["avrora."]),
    ("xalan", "xalan", ["org.apache.xalan.", "org.apache.xpath.", "org.apache.xml."]),
    ("luindex", "luindex", ["org.apache.lucene."]),
    ("fop", "fop", ["org.apache.fop."]),
    ("h2", "h2", ["org.h2."]),
    ("pmd", "pmd", ["net.sourceforge.pmd."]),
]

def read_own(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            parts = c[0].rsplit("|", 2)
            if len(parts) != 3:
                continue
            out[(parts[0], int(parts[1]))] = (c[2], int(c[5]), c[6] == "1", c[7], c[3])
    return out

def get_stats(base_dir):
    stats = {}
    for name, base, _ in BENCH:
        sp = os.path.join(H, "build", "out", "capture-level", f"{name}-false-cap50.sites.json")
        sites = json.load(open(sp))
        p = os.path.join(base_dir, name, base + "-id.own")
        if name == "avrora" and "before-scopelca" in base_dir:
            alt = os.path.join(H, "build", "own", "bench", "avrora-before-scopelca", base + "-id.own")
            if os.path.exists(alt):
                p = alt
        own = read_own(p)
        c = collections.Counter()
        for m, bci, v, w in sites:
            o = own.get((m, bci))
            if o is None:
                c["not_in_spark"] += 1
            else:
                cls, up = o[0], o[1]
                if cls == "UP":
                    c["UP"] += 1
                    c[f"UP{up}"] += 1
                else:
                    c[cls] += 1
        stats[name] = c
    return stats

def get_partitions(base_dir):
    parts = {}
    for name, base, _ in BENCH:
        p = os.path.join(base_dir, name, base + "-id.partition")
        if not os.path.exists(p):
            continue
        # Read header or lines
        # format: method, total, own, up, static_fields, sites...
        method_count = 0
        total_captured = 0
        own_captured = 0
        up_captured = 0
        static_count = 0
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 5 or cols[0] == "GLOBAL":
                    continue
                method_count += 1
                total_captured += int(cols[1])
                own_captured += int(cols[2])
                up_captured += int(cols[3])
                static_count += int(cols[4])
        parts[name] = {
            "methods": method_count,
            "captured": total_captured,
            "own": own_captured,
            "up": up_captured,
            "static_fields": static_count,
        }
    return parts

def main():
    s_before = get_stats(os.path.join(H, "build", "own", "bench-before-scopelca"))
    s_after = get_stats(os.path.join(H, "build", "own", "bench"))
    p_after = get_partitions(os.path.join(H, "build", "own", "bench"))

    print("=" * 95)
    print("PHASE 17 APPLICATION SITES (Spark-Reachable) - BEFORE vs AFTER SCOPE LCA")
    print("=" * 95)
    header = f"{'Benchmark':<10} | {'Before UP':<10} {'After UP':<10} {'Delta UP':<10} | {'Before HEAP':<12} {'After HEAP':<12} {'Delta HEAP':<12}"
    print(header)
    print("-" * 95)
    tot_b_up = tot_a_up = tot_b_hp = tot_a_hp = 0
    for name, _, _ in BENCH:
        b_up, a_up = s_before[name]["UP"], s_after[name]["UP"]
        b_hp, a_hp = s_before[name]["HEAP"], s_after[name]["HEAP"]
        tot_b_up += b_up
        tot_a_up += a_up
        tot_b_hp += b_hp
        tot_a_hp += a_hp
        delta_up = a_up - b_up
        delta_hp = a_hp - b_hp
        print(f"{name:<10} | {b_up:<10} {a_up:<10} {delta_up:<+10} | {b_hp:<12} {a_hp:<12} {delta_hp:<+12}")
    print("-" * 95)
    print(f"{'TOTAL':<10} | {tot_b_up:<10} {tot_a_up:<10} {tot_a_up - tot_b_up:<+10} | {tot_b_hp:<12} {tot_a_hp:<12} {tot_a_hp - tot_b_hp:<+12}")
    print()

    print("=" * 95)
    print("WHOLE-PROGRAM HEAP PARTITIONING RESULTS (B+id)")
    print("=" * 95)
    p_header = f"{'Benchmark':<10} | {'Method Regions':<15} {'Total Captured':<15} {'OWN Sites':<12} {'UP Sites':<10} {'Scoped Statics':<15}"
    print(p_header)
    print("-" * 95)
    for name, _, _ in BENCH:
        if name in p_after:
            d = p_after[name]
            print(f"{name:<10} | {d['methods']:<15} {d['captured']:<15} {d['own']:<12} {d['up']:<10} {d['static_fields']:<15}")
    print("=" * 95)

if __name__ == "__main__":
    main()
