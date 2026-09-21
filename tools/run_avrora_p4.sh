#!/usr/bin/env bash
# run_avrora_p4.sh - avrora on the patch-0004 build: verdict unchanged, then the roots effect.
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
OUT=/tmp/rv/out/dacapo-false-p4
A=/tmp/rv/out/dacapo-false-p3
rm -rf "$OUT"; mkdir -p "$OUT"
t0=$SECONDS
$J/bin/java -Xmx10g -Xss512m -cp "$SOOT:$DIR/build/classes-reason4" main.Main \
   "$J" true "$DIR/../stava/benchmarks/dacapo" Harness "$OUT" true false false \
   > /tmp/rv/avrora-p4.log 2>&1
echo "rc=$?  $((SECONDS-t0))s"
grep "Reasons have been written" /tmp/rv/avrora-p4.log
if [ -f "$A/dacapo.res" ]; then
    echo "== .res multiset diffs vs p3:        $(diff <(sort $A/dacapo.res) <(sort $OUT/dacapo.res) | grep -c '^[<>]')"
    echo "== .reasons col1-4 diffs vs p3:      $(diff <(cut -f1-4 $A/dacapo.reasons | sort) <(cut -f1-4 $OUT/dacapo.reasons | sort) | grep -c '^[<>]')"
else
    echo "== no p3 baseline at $A; verdict check skipped"
fi
echo "== .via groups: $(grep -c "" $OUT/dacapo.via 2>/dev/null)"
echo "== columns: $(awk -F'\t' '{print NF}' $OUT/dacapo.reasons | sort -u | tr '\n' ' ')"
echo "== propagated lines with no group: $(awk -F'\t' '$4 ~ /TRANSITIVE_SUCCESSOR|PARAM_ESCAPES_VIA_SUCCESSOR/ && $5==""' $OUT/dacapo.reasons | grep -c '')"
python3 $DIR/tools/check_invariant.py "$OUT" "avrora p4 roots"
HEAPVIZ_REASON_MODE=raw python3 $DIR/tools/check_invariant.py "$OUT" "avrora p4 raw"
python3 $DIR/tools/roots_effect.py "$OUT" "avrora (app, MarkStoreEscaping=false)" avrora.
