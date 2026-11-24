#!/usr/bin/env bash
# run_param_hubs.sh - tools/python/param_hubs.py on all seven patch-0005 runs (Param-Escape-Hubs-Report).
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
O=$H/build/out/param-hubs
mkdir -p "$O"
ph() {   # ph <name> <cfg> <prefix...>
    local n="$1" c="$2"; shift 2
    python3 "$H/tools/python/param_hubs.py" --run-dir /tmp/rv/p5out/$n-$c --app-info-dir /tmp/rv/p5info/$n-$c \
        --class-prefix "$@" --label "$n $c" --top 15 --json "$O/$n-$c.json" 2>/dev/null
    echo
}
ph avrora  false avrora.
ph avrora  true  avrora.
ph xalan   false org.apache.xalan. org.apache.xpath. org.apache.xml.
ph luindex false org.apache.lucene.
ph fop     false org.apache.fop.
ph h2      false org.h2.
ph pmd     false net.sourceforge.pmd.
echo "PARAM HUBS DONE"
