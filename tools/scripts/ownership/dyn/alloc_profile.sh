#!/usr/bin/env bash
# alloc_profile.sh - allocation weights per site: run one DaCapo 9.12-MR1 benchmark under Flight
# Recorder, which samples allocations (jdk.ObjectAllocationInNewTLAB, ...OutsideTLAB) with the
# allocating frame and its bytecode index, then sum the samples per (method, bci).
#
#   tools/ownership/dyn/alloc_profile.sh avrora [iterations=5] [tlab=4k]
#
# Thread-local buffers are fixed at a small size (-XX:TLABSize, -XX:-ResizeTLAB) so that refills,
# and so samples, are frequent: with the default adaptive sizing a ten-iteration avrora run gave
# 2,508 events and sampled 23 of its 1,304 application sites. The buffer size changes how often
# the JVM samples, not what the program allocates.
#
# Output: build/own/dyn/<bench>/alloc.tsv, read by alloc_weight.py. Same JDK as the static run.
set -u
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
B="${1:?benchmark}"; IT="${2:-5}"; TL="${3:-4k}"
JAR="$DIR/../stava/benchmarks/dacapo/dacapo-9.12-MR1-bach.jar"
W="/tmp/dyn/$B-jfr"; OUT="$DIR/build/own/dyn/$B"
rm -rf "$W"; mkdir -p "$W/cls" "$OUT"
"$J/bin/javac" -nowarn -cp "$J/jre/lib/jfr.jar" -d "$W/cls" "$DIR/tools/ownership/dyn/AllocWeights.java"
cd "$W"
"$J/bin/java" -Xmx1g -XX:-ResizeTLAB -XX:TLABSize="$TL" \
    -XX:StartFlightRecording=filename="$W/alloc.jfr",settings=profile \
    -jar "$JAR" "$B" -n "$IT" > "$W/run.log" 2>&1
echo "benchmark rc=$? ; $(grep -c 'PASSED' "$W/run.log") PASSED lines; $(du -h "$W/alloc.jfr" | cut -f1) recording"
"$J/bin/java" -Xmx2g -cp "$J/jre/lib/jfr.jar:$W/cls" AllocWeights "$W/alloc.jfr" "$OUT/alloc.tsv"
rm -f "$OUT/alloc.json"
