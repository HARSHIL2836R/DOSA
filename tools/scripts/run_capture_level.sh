#!/usr/bin/env bash
# run_capture_level.sh - tools/python/capture_level.py on every patch-0006 run, at the fork's cap of 2
# and at 50, with the hoist candidates and hub sites from param_hubs.py reported separately.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
O=$H/build/out
mkdir -p $O/capture-level
cl() {   # cl <name> <cfg> <prefix...>
    local n="$1" c="$2"; shift 2
    local T="$n-$c"
    for cap in 2 50; do
        python3 $H/tools/python/capture_level.py --run-dir /tmp/rv/p6out/$T --class-prefix "$@" \
            --label "$T up" --cap $cap --objects $O/param-hubs/$T.objects.json \
            --json $O/capture-level/$T-cap$cap.json --sites-out $O/capture-level/$T-cap$cap.sites.json \
            > $O/capture-level/$T-cap$cap.txt 2>&1
    done
}
cl avrora false avrora. &
cl avrora true avrora. &
cl xalan false org.apache.xalan. org.apache.xpath. org.apache.xml. &
cl luindex false org.apache.lucene. &
wait
cl fop false org.apache.fop. &
cl h2 false org.h2. &
cl pmd false net.sourceforge.pmd. &
wait
echo "CAPTURE LEVEL DONE"
