#!/usr/bin/env bash
# run_hotspot_check.sh - which allocation sites C2 removes on each benchmark (tools/hotspot_elim.py).
# DaCapo 9.12-MR1 on the same JDK Stava analysed with, 10 iterations so the hot code reaches C2.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
JAR=$H/../stava/benchmarks/dacapo/dacapo-9.12-MR1-bach.jar
O=/tmp/rv/hotspot
N="${N:-10}"
mkdir -p "$O" "$H/build/out/hotspot"
for b in ${BENCHES:-avrora xalan luindex fop h2 pmd}; do
    echo "########## $b"
    rm -rf "$O/scratch-$b"; mkdir -p "$O/scratch-$b"
    t0=$SECONDS
    ( cd "$O/scratch-$b" && "$J/bin/java" -Xmx4g -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation \
        -XX:LogFile="$O/$b.log" -jar "$JAR" -n "$N" -s default "$b" > "$O/$b.out" 2>&1 )
    echo "   rc=$?  $((SECONDS-t0))s  log $(du -h "$O/$b.log" | cut -f1)"
    grep -h "PASSED\|FAILED" "$O/$b.out" | tail -2 | sed 's/^/   /'
    python3 "$H/tools/hotspot_elim.py" --log "$O/$b.log" --out "$H/build/out/hotspot/$b.tsv" | sed 's/^/   /'
done
echo "HOTSPOT DONE"
