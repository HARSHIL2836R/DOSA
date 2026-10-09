import os, sys
from collections import Counter
sys.path.insert(0, "/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz/extract/python")
from benchmark_scale import build
from info_to_graph import find_reasons_file, read_reasons
d = sys.argv[1]
nodes, _h, _e, _f = build(d, [""], read_reasons(find_reasons_file(d, None)))
bad = Counter(); badr = Counter()
for n in nodes.values():
    st = n.get("escapeStatus")
    if not st: continue
    toks = [t.strip() for t in st.split(",")]
    rs = n.get("escapeReasons") or []
    if "Escape" not in toks and "NoEscape" in toks and rs:
        bad[n["objType"]] += 1
        badr[tuple(sorted(rs))] += 1
print("NoEscape-with-reasons by objectType:", dict(bad))
print("their reason sets:")
for k, c in badr.most_common(6):
    print("   %5d  %s" % (c, ",".join(k)))
