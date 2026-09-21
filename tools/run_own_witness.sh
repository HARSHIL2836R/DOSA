#!/usr/bin/env bash
# run_own_witness.sh - tools/own_witness.py on all seven patch-0005 runs.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
B=$H/../stava/benchmarks
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
w() {   # w <name> <cfg> <classes dir> <prefix...>
    local n="$1" c="$2" cls="$3"; shift 3
    echo "########## $n $c"
    python3 "$H/tools/own_witness.py" --info-dir /tmp/rv/p5out/$n-$c --classes "$cls" \
        --class-prefix "$@" --java-home "$JAVA_HOME" 2>/dev/null
}
w avrora  false "$B/dacapo/out"  avrora.
w avrora  true  "$B/dacapo/out"  avrora.
w xalan   false "$B/xalan/out"   org.apache.xalan. org.apache.xpath. org.apache.xml.
w luindex false "$B/luindex/out" org.apache.lucene.
w fop     false "$B/fop/out"     org.apache.fop.
w h2      false "$B/h2/out"      org.h2.
w pmd     false "$B/pmd/out"     net.sourceforge.pmd.
echo "WITNESS DONE"
