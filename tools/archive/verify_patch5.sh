#!/usr/bin/env bash
# verify_patch5.sh - build patch 0005 and check it adds the own/inherited split and nothing else.
#
# Per corpus program, both MarkStoreEscaping values, against the patch-0004 runs:
#   .res      line multiset identical                         (the verdict does not change)
#   .reasons  tools/python/compare_reasons_p4_p5.py: 7 columns, columns 1-4 identical, column-5
#             pointer sets identical, own a subset of all
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
JAVA_HOME_STAVA=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
W=/tmp/rv/p5
mkdir -p "$W"

echo "== compile stava-src-reason5"
rm -rf "$DIR/build/classes-reason5"; mkdir -p "$DIR/build/classes-reason5"
"$JAVA_HOME_STAVA/bin/javac" -nowarn -cp "$SOOT" \
    -sourcepath "$DIR/build/stava-src-reason5" -d "$DIR/build/classes-reason5" \
    "$DIR/build/stava-src-reason5/main/Main.java" 2>&1 | grep -v '^Note:' | head -20
[ -f "$DIR/build/classes-reason5/main/Main.class" ] || { echo "COMPILE FAILED"; exit 1; }
echo "   ok"

PROGS="${PROGS:-E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02}"
for cfg in false true; do
    echo
    echo "== corpus, MarkStoreEscaping=$cfg"
    for p in $PROGS; do
        old=/tmp/rv/p4/$p-new; [ "$cfg" = true ] && old=/tmp/rv/p4/$p-true
        new=$W/$p-$cfg
        rm -rf "$new"; mkdir -p "$new"
        "$JAVA_HOME_STAVA/bin/java" -Xmx6g -Xss512m -cp "$SOOT:$DIR/build/classes-reason5" main.Main \
            "$JAVA_HOME_STAVA" false "$DIR/build/$p" "$p" "$new" true false "$cfg" > "$new.log" 2>&1 \
            || { echo "   $p RUN FAILED"; continue; }
        dres=$(diff <(sort "$old/$p.res") <(sort "$new/$p.res") | grep -c '^[<>]')
        printf "   .res diffs %2d  " "$dres"
        python3 "$DIR/tools/python/compare_reasons_p4_p5.py" "$old" "$new" "$p"
    done
done
