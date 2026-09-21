#!/bin/bash
# build.sh — compile, analyse, extract and render one corpus program, both configurations.
#
#   ./build.sh M01_mixed M01 "M01 Box Item Node" "<M01: void main(java.lang.String[])>"
#
# There is a Makefile with the same targets, but `make` is NOT installed on this host and
# cannot be (no sudo, no apt), so this script is what was actually run and is the artefact of
# record. The Makefile is provided for hosts that have make.
#
# stava/ and Region-Based-Object-Allocation-in-Java/ are reference checkouts and are never
# written to. Every Stava configuration is compiled from a copy under build/.
#
# PHASE 11. The two configurations are now produced from ONE instrumented build and selected
# at run time by argv[7] (MarkStoreEscaping), rather than from two separately patched source
# trees. The instrumentation is patches/0002-escape-reasons.patch, which also makes that flag
# reachable from the command line; before it, changing the flag was an edit and a recompile,
# which is the only reason patches/0001-store-escape-off.patch had to exist.
#
#   USE_PATCH=1 ./build.sh ...  reproduces phases 1-10 exactly: uninstrumented sources, the
#                               pye configuration from patch 0001 rather than from argv[7],
#                               and no .reasons file and no reason figures.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
JAVA_HOME_STAVA="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
JDK_LABEL="${JDK_LABEL:-Temurin 8u502-b07}"
HEAP="${HEAP:-3g}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
USE_PATCH="${USE_PATCH:-0}"

CORPUS="${1:?corpus dir name, e.g. M01_mixed}"
MAIN="${2:?main class, e.g. M01}"
CLASSES="${3:?space-separated app classes}"
FOCUS="${4:-}"

SRC="$DIR/corpus/$CORPUS"
CLS="$DIR/build/$MAIN"

echo "== 1. stava sources: out-of-tree copies (checkout untouched)"
if [ ! -d "$DIR/build/stava-src-upstream" ]; then
    cp -r "$DIR/../stava/src" "$DIR/build/stava-src-upstream"
    find "$DIR/build/stava-src-upstream" -name '*.class' -delete
fi
if [ ! -d "$DIR/build/stava-src-pye" ]; then
    rm -rf "$DIR/build/pyework"; mkdir -p "$DIR/build/pyework"
    cp -r "$DIR/build/stava-src-upstream" "$DIR/build/pyework/src"
    ( cd "$DIR/build/pyework" && patch -p1 < "$DIR/patches/0001-store-escape-off.patch" )
    mv "$DIR/build/pyework/src" "$DIR/build/stava-src-pye"; rm -rf "$DIR/build/pyework"
fi
if [ ! -d "$DIR/build/stava-src-reason" ]; then
    rm -rf "$DIR/build/rwork"; mkdir -p "$DIR/build/rwork"
    cp -r "$DIR/build/stava-src-upstream" "$DIR/build/rwork/src"
    ( cd "$DIR/build/rwork" && patch -p1 < "$DIR/patches/0002-escape-reasons.patch" )
    mv "$DIR/build/rwork/src" "$DIR/build/stava-src-reason"; rm -rf "$DIR/build/rwork"
fi

echo "== 2. build stava"
if [ "$USE_PATCH" = "1" ]; then TREES="upstream pye"; else TREES="reason"; fi
for cfg in $TREES; do
    rm -rf "$DIR/build/classes-$cfg"; mkdir -p "$DIR/build/classes-$cfg"
    "$JAVA_HOME_STAVA/bin/javac" -nowarn -cp "$SOOT" \
        -sourcepath "$DIR/build/stava-src-$cfg" -d "$DIR/build/classes-$cfg" \
        "$DIR/build/stava-src-$cfg/main/Main.java"
done

echo "== 3. compile the corpus program"
rm -rf "$CLS"; mkdir -p "$CLS"
"$JAVA_HOME_STAVA/bin/javac" -source 8 -target 8 -d "$CLS" "$SRC"/*.java 2>&1 \
    | grep -v 'bootstrap class path' || true

echo "== 4. analyse, extract, render"
mkdir -p "$DIR/build/logs" "$DIR/render/figures"
for cfg in upstream pye; do
    OUT="$DIR/build/out/$MAIN-$cfg"
    rm -rf "$OUT"; mkdir -p "$OUT"
    if [ "$cfg" = "pye" ]; then
        LABEL="MarkStoreEscaping=false (patched)"; MSE=false
    else
        LABEL="MarkStoreEscaping=true (upstream default)"; MSE=true
    fi

    echo "-- stava run: $cfg (~45-60s, almost all of it Spark over the JDK)"
    if [ "$USE_PATCH" = "1" ]; then
        # phases 1-10 reproduction: the flag comes from the source tree, not from argv
        "$JAVA_HOME_STAVA/bin/java" -Xmx"$HEAP" -cp "$SOOT:$DIR/build/classes-$cfg" \
            main.Main "$JAVA_HOME_STAVA" false "$CLS" "$MAIN" "$OUT" \
            > "$DIR/build/logs/$MAIN-$cfg.log" 2>&1
        REASON_ARGS=""
    else
        # argv[5] and argv[6] are pinned to their upstream defaults so that argv[7] is the
        # ONLY thing that differs between the two configurations.
        "$JAVA_HOME_STAVA/bin/java" -Xmx"$HEAP" -cp "$SOOT:$DIR/build/classes-reason" \
            main.Main "$JAVA_HOME_STAVA" false "$CLS" "$MAIN" "$OUT" true false "$MSE" \
            > "$DIR/build/logs/$MAIN-$cfg.log" 2>&1
        REASON_ARGS="--require-reasons"
    fi

    python3 "$DIR/extract/info_to_graph.py" --info-dir "$OUT" --classes $CLASSES \
        --class-dir "$CLS" --javap "$JAVA_HOME_STAVA/bin/javap" \
        --config "$LABEL" --jdk "$JDK_LABEL" --definition S $REASON_ARGS \
        --out "$OUT/graph.json"

    for def in S C; do
        python3 "$DIR/render/graph_to_svg.py" --graph "$OUT/graph.json" \
            --definition "$def" ${FOCUS:+--focus "$FOCUS"} --hide-params \
            --title "$MAIN - equi-escape sets under definition $def ($LABEL)" \
            --svg "$DIR/render/figures/$MAIN-$cfg-$def.svg" \
            --dot "$DIR/render/figures/$MAIN-$cfg-$def.dot"
    done

    # interprocedural view: per-method PTGs stitched into one heap graph
    python3 "$DIR/extract/interprocedural.py" --graph "$OUT/graph.json" \
        --out "$OUT/graph-interproc.json"
    for def in S C; do
        python3 "$DIR/render/graph_to_svg.py" --graph "$OUT/graph-interproc.json" \
            --definition "$def" \
            --title "$MAIN - interprocedural PTG, equi-escape set $def ($LABEL)" \
            --svg "$DIR/render/figures/$MAIN-$cfg-interproc-$def.svg" \
            --dot "$DIR/render/figures/$MAIN-$cfg-interproc-$def.dot"
    done

    # the three escape-reason figures; skipped under USE_PATCH=1, which has no .reasons
    if [ "$USE_PATCH" != "1" ]; then
        python3 "$DIR/render/reason_figures.py" --graph "$OUT/graph.json" \
            --title "$MAIN ($LABEL)" \
            --out-prefix "$DIR/render/figures/$MAIN-$cfg-reason"
    fi
done

echo
echo "figures: $DIR/render/figures/"
