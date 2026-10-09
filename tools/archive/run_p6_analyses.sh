#!/usr/bin/env bash
# run_p6_analyses.sh - everything that reads a patch-0006 run, per benchmark:
#   alloc_unit.py     fix F4 measured: nodes vs allocation sites, aliases, what stays outside
#   param_hubs.py     parameter hubs and hoist candidates, now also as object lists
#   capture_level.py  frames up (Kavya2's walk), at the fork's cap of 2 and at 50
#   frame_depth.py    frames down (Meet 5's frame-depth axis)
#   hotspot_vs_sites.py  of the hub sites and hoist candidates, how many C2 already removes
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
O=$H/build/out
mkdir -p $O/alloc-unit $O/param-hubs $O/capture-level $O/frame-depth $O/hotspot
go() {   # go <name> <cfg> <prefix...>
    local n="$1" c="$2"; shift 2
    local R=/tmp/rv/p6out/$n-$c I=/tmp/rv/p6info/$n-$c T="$n-$c"
    echo "################ $T"
    python3 $H/tools/python/alloc_unit.py --info-dir $I --class-prefix "$@" --label "$T" --json $O/alloc-unit/$T.json
    python3 $H/tools/python/param_hubs.py --run-dir $R --app-info-dir $I --class-prefix "$@" --label "$T" \
        --top 15 --json $O/param-hubs/$T-p6.json --objects-out $O/param-hubs/$T.objects.json 2>/dev/null \
        | sed -n '1,/-- hoisting, optimistic/p' | tail -6
    for cap in 2 50; do
        python3 $H/tools/python/capture_level.py --run-dir $R --class-prefix "$@" --label "$T up" --cap $cap \
            --objects $O/param-hubs/$T.objects.json --json $O/capture-level/$T-cap$cap.json
    done
    python3 $H/tools/python/frame_depth.py --run-dir $R --class-prefix "$@" --label "$T down" --json $O/frame-depth/$T.json
    [ -f $O/hotspot/$n.tsv ] && python3 $H/tools/python/hotspot_vs_sites.py --elim $O/hotspot/$n.tsv \
        --objects $O/param-hubs/$T.objects.json --label "$T vs C2" --json $O/hotspot/$T-vs.json
    echo
}
ONLY="${ONLY:-}"
want() { [ -z "$ONLY" ] || case " $ONLY " in *" $1 "*) return 0;; *) return 1;; esac; }
want avrora-false  && go avrora  false avrora.
want avrora-true   && go avrora  true  avrora.
want xalan-false   && go xalan   false org.apache.xalan. org.apache.xpath. org.apache.xml.
want luindex-false && go luindex false org.apache.lucene.
want fop-false     && go fop     false org.apache.fop.
want h2-false      && go h2      false org.h2.
want pmd-false     && go pmd     false net.sourceforge.pmd.
echo "P6 ANALYSES DONE"
