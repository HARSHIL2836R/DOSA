#!/usr/bin/env bash
# verify_patch4.sh - build patch 0004 and check it adds successor pointers and nothing else.
#
# Two checks per corpus program, MarkStoreEscaping=false, against the patch-0003 build:
#   .res      line multiset identical        (constraint 1: the verdict does not change)
#   .reasons  columns 1-4 identical          (0004 only appends column 5, GROUP, and writes .via)
# The patch-0003 outputs are reused from verify_patch3.sh (/tmp/rv/p3/<prog>-new) when present.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
JAVA_HOME_STAVA=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
W=/tmp/rv/p4
mkdir -p "$W"

echo "== compile stava-src-reason4"
rm -rf "$DIR/build/classes-reason4"; mkdir -p "$DIR/build/classes-reason4"
"$JAVA_HOME_STAVA/bin/javac" -nowarn -cp "$SOOT" \
    -sourcepath "$DIR/build/stava-src-reason4" -d "$DIR/build/classes-reason4" \
    "$DIR/build/stava-src-reason4/main/Main.java" 2>&1 | grep -v '^Note:' | head -20
[ -f "$DIR/build/classes-reason4/main/Main.class" ] || { echo "COMPILE FAILED"; exit 1; }
echo "   ok"

run() {   # run <prog> <classesdir> <outdir> <mse>
    "$JAVA_HOME_STAVA/bin/java" -Xmx6g -Xss512m -cp "$SOOT:$2" main.Main \
        "$JAVA_HOME_STAVA" false "$DIR/build/$1" "$1" "$3" true false "$4" \
        > "$W/$1-$(basename $2)-$4.log" 2>&1
    return $?
}

PROGS="${PROGS:-E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02}"
echo
echo "== run every corpus program, MarkStoreEscaping=false"
for p in $PROGS; do
    [ -d "$DIR/build/$p" ] || { echo "   skip $p (no classes)"; continue; }
    old=/tmp/rv/p3/$p-new
    if [ ! -f "$old/$p.res" ]; then
        old="$W/$p-old"; rm -rf "$old"; mkdir -p "$old"
        run "$p" "$DIR/build/classes-reason3" "$old" false || { echo "   $p OLD RUN FAILED"; continue; }
    fi
    new="$W/$p-new"; rm -rf "$new"; mkdir -p "$new"
    run "$p" "$DIR/build/classes-reason4" "$new" false || { echo "   $p NEW RUN FAILED"; continue; }
    [ -f "$new/$p.res" ] || { echo "   $p NO .res"; continue; }

    dres=$(diff <(sort "$old/$p.res") <(sort "$new/$p.res") | grep -c '^[<>]')
    drsn=$(diff <(cut -f1-4 "$old/$p.reasons" | sort) <(cut -f1-4 "$new/$p.reasons" | sort) | grep -c '^[<>]')
    cols=$(awk -F'\t' '{print NF}' "$new/$p.reasons" | sort -u | tr '\n' ' ')
    via=$(awk -F'\t' '$5!=""' "$new/$p.reasons" | grep -c '')
    prop=$(grep -cE 'TRANSITIVE_SUCCESSOR|PARAM_ESCAPES_VIA_SUCCESSOR' "$new/$p.reasons")
    printf "   %-4s .res diffs %3d   .reasons col1-4 diffs %3d   columns: %s  propagated %4d  in a group %4d  .via groups %3d\n" \
        "$p" "$dres" "$drsn" "$cols" "$prop" "$via" "$(grep -c "" "$new/$p.via" 2>/dev/null)"
done
