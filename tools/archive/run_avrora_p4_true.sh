#!/usr/bin/env bash
# run_avrora_p4_true.sh - avrora, MarkStoreEscaping=true, patch-0004 build (objective O9).
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
OUT=/tmp/rv/out/dacapo-true-p4
A=/tmp/rv/out/dacapo-true
rm -rf "$OUT"; mkdir -p "$OUT"
t0=$SECONDS
$J/bin/java -Xmx10g -Xss512m -cp "$SOOT:$DIR/build/classes-reason4" main.Main \
   "$J" true "$DIR/../stava/benchmarks/dacapo" Harness "$OUT" true false true \
   > /tmp/rv/avrora-p4-true.log 2>&1
echo "rc=$?  $((SECONDS-t0))s"
grep "Reasons have been written" /tmp/rv/avrora-p4-true.log
[ -f "$A/dacapo.res" ] && echo "== .res multiset diffs vs pre-0003 true run: $(diff <(sort $A/dacapo.res) <(sort $OUT/dacapo.res) | grep -c '^[<>]')"
