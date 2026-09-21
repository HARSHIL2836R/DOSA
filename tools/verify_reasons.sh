#!/bin/bash
# verify_reasons.sh — the constraint-1 check for patches/0002-escape-reasons.patch.
#
# "The escape verdict must not change." <dirname>.res is the JVM-consumable artefact, so the
# check is: run every stava test under the uninstrumented and the instrumented build and diff
# the .res files.
#
#   ./tools/verify_reasons.sh            run all three passes then diff
#   ./tools/verify_reasons.sh diff-only  diff passes that already ran
#
# THREE passes, not two, and the third is the point. printResForJVM iterates a HashMap keyed by
# SootMethod, so raw LINE ORDER in .res is not guaranteed stable from one run to the next even
# with identical code. Running the UNINSTRUMENTED build twice (baseA, baseB) measures that
# instability directly, so a byte difference between baseA and reason can be attributed to the
# right cause instead of guessed at. Without baseB there is no way to tell "the instrumentation
# changed the verdict" from "a HashMap iterated differently".
#
# stava/ is never written to: sources are copied to $WORK/tests and output goes to $WORK/out.

set -u

DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAVA="$DIR/../stava"
JAVA_HOME_STAVA="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$STAVA/soot/sootclasses-trunk-jar-with-dependencies.jar"
WORK="${WORK:-/tmp/rv}"
HEAP="${HEAP:-3g}"

# test12 and test17 need drivers the plain normal() Soot-arg path does not provide; see
# stava/scripts/run-all-tests.sh, which skips the same two.
SKIP="test12 test17"

run_pass () {   # run_pass <classes-dir> <label> [extra argv...]
    local CLASSES=$1 LABEL=$2; shift 2
    mkdir -p "$WORK/tests" "$WORK/out/$LABEL" "$WORK/logs/$LABEL"
    for d in "$STAVA"/tests/*/; do
        local name; name=$(basename "$d")
        case " $SKIP " in *" $name "*) echo "$name SKIPPED(special driver)"; continue;; esac
        local src="$WORK/tests/$name"
        if [ ! -f "$src/.compiled" ]; then
            rm -rf "$src"; mkdir -p "$src"
            cp "$d"/*.java "$src"/ 2>/dev/null || { echo "$name NO_SOURCE"; continue; }
            local mc; mc=$(grep -l "static void main" "$src"/*.java 2>/dev/null | head -1)
            mc=$(basename "${mc:-Main.java}" .java)
            "$JAVA_HOME_STAVA/bin/javac" -nowarn -source 8 -target 8 -cp "$src" -d "$src" \
                "$src"/*.java > "$WORK/logs/$name.compile" 2>&1 \
                || { echo "$name COMPILE_FAIL"; continue; }
            echo "$mc" > "$src/.compiled"
        fi
        local mc; mc=$(cat "$src/.compiled")
        local out="$WORK/out/$LABEL/$name"; rm -rf "$out"; mkdir -p "$out"
        local s; s=$(date +%s)
        "$JAVA_HOME_STAVA/bin/java" -Xmx"$HEAP" -cp "$SOOT:$CLASSES" \
            main.Main "$JAVA_HOME_STAVA" false "$src" "$mc" "$out" "$@" \
            > "$WORK/logs/$LABEL/$name.log" 2>&1
        echo "$name rc=$? $(( $(date +%s) - s ))s res=$( [ -f "$out/$name.res" ] && wc -l < "$out/$name.res" || echo 0 ) reasons=$( [ -f "$out/$name.reasons" ] && wc -l < "$out/$name.reasons" || echo 0 )"
    done
    echo "== done $LABEL"
}

diff_pass () { # diff_pass <labelA> <labelB>
    local A=$1 B=$2 n=0 same_b=0 same_s=0 bad=""
    printf "%-10s %10s %10s\n" test bytes as-line-set
    for d in "$WORK/out/$A"/*/; do
        local t; t=$(basename "$d")
        local fa="$d/$t.res" fb="$WORK/out/$B/$t/$t.res"
        [ -f "$fa" ] && [ -f "$fb" ] || { printf "%-10s %10s %10s\n" "$t" MISSING MISSING; continue; }
        n=$((n+1))
        local bs ss
        if cmp -s "$fa" "$fb"; then bs=IDENTICAL; same_b=$((same_b+1)); else bs=DIFFER; fi
        if diff -q <(sort "$fa") <(sort "$fb") >/dev/null; then ss=IDENTICAL; same_s=$((same_s+1));
        else ss=DIFFER; bad="$bad $t"; fi
        printf "%-10s %10s %10s\n" "$t" "$bs" "$ss"
    done
    echo "$A vs $B: $n compared, $same_b byte-identical, $same_s identical as line sets"
    [ -n "$bad" ] && echo "SET-DIFFERENT:$bad"
    return 0
}

if [ "${1:-}" != "diff-only" ]; then
    for cfg in upstream reason; do
        rm -rf "$WORK/classes-$cfg"; mkdir -p "$WORK/classes-$cfg"
        "$JAVA_HOME_STAVA/bin/javac" -nowarn -cp "$SOOT" \
            -sourcepath "$DIR/build/stava-src-$cfg" -d "$WORK/classes-$cfg" \
            "$DIR/build/stava-src-$cfg/main/Main.java" || exit 1
    done
    cp -r "$WORK/classes-upstream" "$WORK/classes-upstreamB"
    run_pass "$WORK/classes-upstream"  baseA  > "$WORK/pass-baseA.txt"  2>&1
    run_pass "$WORK/classes-upstreamB" baseB  > "$WORK/pass-baseB.txt"  2>&1
    # argv 5,6,7 pinned to the upstream compiled-in defaults, so the ONLY difference from the
    # baseline passes is the instrumentation itself.
    run_pass "$WORK/classes-reason"    reason true false true > "$WORK/pass-reason.txt" 2>&1
fi

echo "=== run-to-run stability of the UNINSTRUMENTED build (baseA vs baseB) ==="
diff_pass baseA baseB
echo
echo "=== constraint 1: uninstrumented vs instrumented (baseA vs reason) ==="
diff_pass baseA reason
