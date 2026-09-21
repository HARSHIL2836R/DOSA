#!/usr/bin/env bash
# verify_patch3.sh - build patch 0003 and check it changes reasons but not the verdict.
#
# Constraint 1 from the original prompt: the escape verdict must not change. The test is a
# diff of the .res LINE MULTISET before and after, over every corpus program, because
# printResForJVM iterates a HashMap and byte order is not stable even between two runs of the
# same build (F11.1).
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
JAVA_HOME_STAVA=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
W=/tmp/rv/p3
mkdir -p "$W"

echo "== compile stava-src-reason3"
rm -rf "$DIR/build/classes-reason3"; mkdir -p "$DIR/build/classes-reason3"
"$JAVA_HOME_STAVA/bin/javac" -nowarn -cp "$SOOT" \
    -sourcepath "$DIR/build/stava-src-reason3" -d "$DIR/build/classes-reason3" \
    "$DIR/build/stava-src-reason3/main/Main.java" 2>&1 | head -20
[ -f "$DIR/build/classes-reason3/main/Main.class" ] || { echo "COMPILE FAILED"; exit 1; }
echo "   ok"

run() {   # run <prog> <classesdir> <outdir> <mse>
    "$JAVA_HOME_STAVA/bin/java" -Xmx6g -Xss512m -cp "$SOOT:$2" main.Main \
        "$JAVA_HOME_STAVA" false "$DIR/build/$1" "$1" "$3" true false "$4" \
        > "$W/$1-$(basename $2)-$4.log" 2>&1
    return $?
}

PROGS="E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02"
echo
echo "== run every corpus program on both builds, MarkStoreEscaping=false"
for p in $PROGS; do
    [ -d "$DIR/build/$p" ] || { echo "   skip $p (no classes)"; continue; }
    rm -rf "$W/$p-old" "$W/$p-new"; mkdir -p "$W/$p-old" "$W/$p-new"
    run "$p" "$DIR/build/classes-reason"  "$W/$p-old" false; a=$?
    run "$p" "$DIR/build/classes-reason3" "$W/$p-new" false; b=$?
    if [ $a -ne 0 ] || [ $b -ne 0 ]; then echo "   $p RUN FAILED old=$a new=$b"; continue; fi
    o="$W/$p-old/$p.res"; n="$W/$p-new/$p.res"
    if [ ! -f "$o" ] || [ ! -f "$n" ]; then echo "   $p NO .res"; continue; fi
    d=$(diff <(sort "$o") <(sort "$n") | grep -c '^[<>]')
    ro=$(grep -c '' "$o"); rn=$(grep -c '' "$n")
    # reason deltas
    xo=$(grep -c 'RETURNED' "$W/$p-old/$p.reasons" 2>/dev/null || echo 0)
    xn=$(grep -c 'RETURNED' "$W/$p-new/$p.reasons" 2>/dev/null || echo 0)
    printf "   %-4s .res lines %5d/%5d  multiset diffs %3d   RETURNED %4d -> %4d\n" \
        "$p" "$ro" "$rn" "$d" "$xo" "$xn"
done
