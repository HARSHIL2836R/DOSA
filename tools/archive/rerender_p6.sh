#!/usr/bin/env bash
# rerender_p6.sh - redraw only the reason figures from the graphs run_dashboard_p6.sh extracted.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
FIG=$H/render/figures
export HEAPVIZ_REASON_MODE=roots
for b in avrora-false avrora-true xalan-false luindex-false fop-false h2-false pmd-false; do
    n=${b%-*}; c=${b##*-}
    python3 $H/render/python/reason_figures.py --graph $H/build/out/$n-p6-$c/graph-full.json \
        --title "$n - MarkStoreEscaping=$c (patch 0006, roots mode)" --out-prefix $FIG/$n-p6-$c-reason > /dev/null \
        || echo "FAILED $b"
done
for p in E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02; do
    for c in false true; do
        python3 $H/render/python/reason_figures.py --graph $H/build/out/$p-p6-$c/graph.json \
            --title "$p (MarkStoreEscaping=$c (patch 0006, roots mode))" --out-prefix $FIG/$p-p6-$c-reason > /dev/null \
            || echo "FAILED $p $c"
    done
done
python3 $H/tools/python/scan_figures.py "$FIG" "*-p6-*"
echo "RERENDER DONE"
