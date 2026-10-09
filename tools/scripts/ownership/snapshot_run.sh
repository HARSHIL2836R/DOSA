#!/usr/bin/env bash
# snapshot_run.sh - D0 of the Ownership Trees design note (§6.2): run one DaCapo 9.12-MR1
# benchmark, take live heap dumps while it runs, and compute each dump's ownership tree.
#
#   tools/scripts/ownership/snapshot_run.sh avrora [dumps=6] [interval_s=2] [iterations=20]
#
# Dumps start once the second iteration begins, so class loading and the first warmup are not
# what gets measured. Each dump is summarised by hprof_tree.py into build/own/dyn/<bench>/; the
# .hprof files stay in /tmp/dyn/<bench>/ (WSL) and the first one is kept, the rest deleted.
set -u
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
B="${1:?benchmark}"; N="${2:-6}"; T="${3:-2}"; IT="${4:-20}"
JAR="$DIR/../stava/benchmarks/dacapo/dacapo-9.12-MR1-bach.jar"
W="/tmp/dyn/$B"; OUT="$DIR/build/own/dyn/$B"
rm -rf "$W"; mkdir -p "$W" "$OUT"
cd "$W"
"$J/bin/java" -Xmx1g -jar "$JAR" "$B" -n "$IT" > "$W/run.log" 2>&1 &
PID=$!
until grep -q "starting warmup 2" "$W/run.log" 2>/dev/null || ! kill -0 $PID 2>/dev/null; do sleep 0.5; done
k=0
while [ $k -lt "$N" ] && kill -0 $PID 2>/dev/null; do
    k=$((k + 1))
    "$J/bin/jmap" -dump:live,format=b,file="$W/dump-$k.hprof" $PID > /dev/null 2>&1 \
        && echo "dump $k at $(date +%T), $(du -h "$W/dump-$k.hprof" | cut -f1)"
    sleep "$T"
done
wait $PID
echo "benchmark rc=$? ; $(grep -c 'PASSED' "$W/run.log") PASSED lines"
for f in "$W"/dump-*.hprof; do
    python3 "$DIR/tools/python/ownership/dyn/hprof_tree.py" "$f" --json "$OUT/$(basename "$f" .hprof).json" \
        > "$OUT/$(basename "$f" .hprof).txt" 2>&1
    echo "== $(basename "$f")"; sed -n '2,8p' "$OUT/$(basename "$f" .hprof).txt"
    [ "$(basename "$f")" = "dump-1.hprof" ] || rm -f "$f"
done
