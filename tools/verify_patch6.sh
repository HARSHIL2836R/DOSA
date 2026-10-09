#!/usr/bin/env bash
# verify_patch6.sh - build patch 0006 and check it adds .alloc/.allocsets and changes nothing else.
#
# Per corpus program, both MarkStoreEscaping values, against the patch-0005 runs in /tmp/rv/p5:
#   .res      line multiset identical     (the verdict does not change)
#   .reasons  byte-identical              (the reasons do not change)
#   .via      byte-identical
# then prints each program's .alloc so the site mapping can be read against the source.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
CLS=$DIR/build/classes-reason6
W=/tmp/rv/p6
mkdir -p "$W"

echo "== compile stava-src-reason6"
rm -rf "$CLS"; mkdir -p "$CLS"
"$J/bin/javac" -nowarn -cp "$SOOT" -sourcepath "$DIR/build/stava-src-reason6" -d "$CLS" \
    "$DIR/build/stava-src-reason6/main/Main.java" 2>&1 | grep -v '^Note:' | head -20
[ -f "$CLS/main/AllocSites.class" ] || { echo "COMPILE FAILED"; exit 1; }
echo "   ok"

PROGS="${PROGS:-E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02}"
SHOW="${SHOW:-}"
for cfg in false true; do
    echo
    echo "== corpus, MarkStoreEscaping=$cfg"
    for p in $PROGS; do
        old=$DIR/../tmp-missing; old=/tmp/rv/p5/$p-$cfg
        new=$W/$p-$cfg
        rm -rf "$new"; mkdir -p "$new"
        "$J/bin/java" -Xmx6g -Xss512m -cp "$SOOT:$CLS" main.Main \
            "$J" false "$DIR/build/$p" "$p" "$new" true false "$cfg" > "$new.log" 2>&1 \
            || { echo "   $p RUN FAILED"; continue; }
        dres=$(diff <(sort "$old/$p.res") <(sort "$new/$p.res") | grep -c '^[<>]')
        cmp -s "$old/$p.reasons" "$new/$p.reasons" && rs=same || rs=DIFF
        cmp -s "$old/$p.via" "$new/$p.via" && vs=same || vs=DIFF
        printf "   %-4s .res diffs %2d  .reasons %s  .via %s  " "$p" "$dres" "$rs" "$vs"
        grep -h "Allocation sites have been written" "$new.log" | sed 's/Allocation sites have been written: //'
        [ -n "$SHOW" ] && [ "$cfg" = false ] && case " $SHOW " in *" $p "*)
            echo "   ---- $p.alloc"; sed 's/^/      /' "$new/$p.alloc"
            echo "   ---- $p.allocsets"; sed 's/^/      /' "$new/$p.allocsets";;
        esac
    done
done
