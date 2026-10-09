#!/usr/bin/env bash
# run_corpus.sh - the static ownership tree on corpus programs, with and without identity returns.
#
#   tools/scripts/ownership/run_corpus.sh O01 O02 ...     programs by main class; default: every O, E, M
#
# Each program is compiled into build/<MAIN> the same way heapviz/build.sh does, then analysed
# twice (~45-60 s each, almost all of it Spark over the JDK). Output: build/own/<MAIN>/.
set -uo pipefail
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
CP="$SOOT:$DIR/build/classes-reason6:$DIR/build/ownership-classes"

progs=("$@")
if [ ${#progs[@]} -eq 0 ]; then
    progs=()
    for d in "$DIR"/corpus/*/; do b=$(basename "$d"); progs+=("${b%%_*}"); done
fi

for MAIN in "${progs[@]}"; do
    SRC=$(ls -d "$DIR"/corpus/"$MAIN"_*/ | head -1)
    CLS="$DIR/build/$MAIN"
    rm -rf "$CLS"; mkdir -p "$CLS"
    "$J/bin/javac" -source 8 -target 8 -d "$CLS" "$SRC"*.java 2>&1 | grep -v 'bootstrap class path' || true
    OUT="$DIR/build/own/$MAIN"
    rm -rf "$OUT"; mkdir -p "$OUT"
    for id in false true; do
        echo "== $MAIN identityReturns=$id"
        "$J/bin/java" -Xmx3g -Downership.identityReturns=$id -Downership.check=1000 -cp "$CP" \
            heapviz.OwnershipTree "$J" false "$CLS" "$MAIN" "$OUT" > "$OUT/run-$id.log" 2>&1
        echo "   rc=$?"
        grep '^\[ownership\]' "$OUT/run-$id.log" | grep -v 'soot args' | sed 's/^/   /'
    done
done
