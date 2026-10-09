#!/usr/bin/env bash
# run_inline_sweep.sh - how much the library-inlining result depends on its two limits: depth
# (rounds of inlining) and the largest JDK body copied (units). Output:
# build/own/sweep/<bench>-d<depth>-u<units>/, read with
#   alloc_weight.py --bench <bench> --inline-dir build/own/sweep/<bench>-d<depth>-u<units>
#
#   BENCHES="avrora pmd" tools/scripts/ownership/run_inline_sweep.sh     (detach it: setsid nohup ...)
set -u
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
CP="$SOOT:$DIR/build/classes-reason6:$DIR/build/ownership-classes"
B="$DIR/../stava/benchmarks"
declare -A IN=([avrora]=dacapo [xalan]=xalan [luindex]=luindex [fop]=fop [h2]=h2 [pmd]=pmd)
CONFIGS="${CONFIGS:-1:60 2:60 3:60 4:60 3:30 3:120}"
for b in ${BENCHES:-avrora pmd}; do
    for c in $CONFIGS; do
        d=${c%%:*}; u=${c##*:}
        out="$DIR/build/own/sweep/$b-d$d-u$u"
        mkdir -p "$out"
        t0=$SECONDS
        "$J/bin/java" -Xmx10g -Xss512m -Downership.identityReturns=true -Downership.inlineLib=true \
            -Downership.inlineDepth=$d -Downership.inlineUnits=$u -Downership.check=20 -cp "$CP" \
            heapviz.OwnershipTree "$J" true "$B/${IN[$b]}" Harness "$out" > "$out/run.log" 2>&1
        echo "$b depth=$d units=$u rc=$? $((SECONDS-t0))s $(grep -h 'reachability check' "$out/run.log" | cut -c1-120)"
    done
done
echo "SWEEP DONE"
