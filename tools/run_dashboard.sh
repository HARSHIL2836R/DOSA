#!/usr/bin/env bash
# run_dashboard.sh - regenerate every figure and every explorer from the patch-0003 runs.
#
# Everything on disk before this was produced by the pre-0003 build, where RETURNED could not
# appear on a concrete object and was therefore absent from every figure. This re-extracts and
# re-renders all six benchmarks from /tmp/rv/p3info.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
JDK="Temurin 8u502-b07"
CFG="MarkStoreEscaping=false (patch 0003: RETURNED on concrete objects)"
mkdir -p "$H/render/figures"
cd "$H/extract"

one() {   # one <name> <prefix...>
    local n="$1"; shift
    local out="$H/build/out/$n-p3"
    echo
    echo "########## $n"
    python3 benchmark_scale.py --info-dir "/tmp/rv/p3info/$n" --class-prefix "$@" \
        --label "$n (DaCapo 9.12-MR1)" --jdk "$JDK" --config "$CFG" --require-reasons \
        --out-dir "$out" 2>&1 | grep -E "objects \(int|NoEscape share|reasonCount histogram|realReasonCount|single-reason attribution|component blobs|Escape with|NoEscape with" || true

    python3 "$H/render/reason_figures.py" --graph "$out/graph-full.json" \
        --title "$n - $CFG" \
        --out-prefix "$H/render/figures/$n-p3-reason" 2>&1 | tail -3

    python3 "$H/render/graph_to_html.py" --graph "$out/graph-full.json" \
        --title "$n - escape explorer ($CFG)" \
        --out "$H/render/figures/$n-p3-explorer.html" 2>&1 | tail -2
}

one avrora  avrora.
one xalan   org.apache.xalan. org.apache.xpath. org.apache.xml.
one luindex org.apache.lucene.
one fop     org.apache.fop.
one h2      org.h2.
one pmd     net.sourceforge.pmd.

echo
echo "########## artefacts"
ls -la "$H/render/figures/"*-p3-* 2>/dev/null | awk '{printf "   %8s  %s\n", $5, $9}'
