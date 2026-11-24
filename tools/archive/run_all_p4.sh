#!/usr/bin/env bash
# run_all_p4.sh - re-analyse on the patch-0004 build everything the figures are drawn from (fix F1
# of 02-Current-Work/02-Specs/2026-09-14-Viz-Faithfulness-Audit.md).
#
#   benchmarks  xalan luindex fop h2 pmd, MarkStoreEscaping=false (avrora was run by
#               run_avrora_p4.sh and run_avrora_p4_true.sh)
#   corpus      all 13 programs, MarkStoreEscaping=true (the false runs are verify_patch4.sh's)
#
# Every run is checked against its earlier .res; copies go to /tmp/rv/p4info/<name>-<cfg> with the
# .reasons AND the .via, which roots mode needs.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
CLS=$DIR/build/classes-reason4
B=$DIR/../stava/benchmarks
mkdir -p /tmp/rv/p4out /tmp/rv/p4info

bench() {   # bench <name> <input dir> <prefix...>
    local name="$1" indir="$2"; shift 2
    local out=/tmp/rv/p4out/$name-false
    echo "########## $name (MarkStoreEscaping=false)"
    rm -rf "$out"; mkdir -p "$out"
    local t0=$SECONDS
    "$J/bin/java" -Xmx10g -Xss512m -cp "$SOOT:$CLS" main.Main \
        "$J" true "$indir" Harness "$out" true false false > "$out.log" 2>&1
    local rc=$?
    echo "   stava rc=$rc  $((SECONDS-t0))s"
    grep -h "Reasons have been written" "$out.log" | sed 's/^/   /'
    [ $rc -eq 0 ] || return 1
    local old; old=$(ls /tmp/rv/p3out/$name/*.res 2>/dev/null | head -1)
    local new; new=$(ls "$out"/*.res | head -1)
    [ -f "$old" ] && echo "   .res multiset diffs vs p3: $(diff <(sort "$old") <(sort "$new") | grep -c '^[<>]')"
    local info=/tmp/rv/p4info/$name-false
    rm -rf "$info"; mkdir -p "$info"
    for p in "$@"; do cp "$out/$p"*.info "$info/" 2>/dev/null; done
    cp "$out"/*.reasons "$out"/*.via "$info/"
    echo "   app .info files: $(ls "$info"/*.info 2>/dev/null | wc -l)"
}

bench xalan   "$B/xalan"   org.apache.xalan. org.apache.xpath. org.apache.xml.
bench luindex "$B/luindex" org.apache.lucene.
bench fop     "$B/fop"     org.apache.fop.
bench h2      "$B/h2"      org.h2.
bench pmd     "$B/pmd"     net.sourceforge.pmd.

echo
echo "########## corpus, MarkStoreEscaping=true"
for p in E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02; do
    out=/tmp/rv/p4/$p-true
    rm -rf "$out"; mkdir -p "$out"
    "$J/bin/java" -Xmx6g -Xss512m -cp "$SOOT:$CLS" main.Main \
        "$J" false "$DIR/build/$p" "$p" "$out" true false true > "$out.log" 2>&1
    rc=$?
    old=$DIR/build/out/$p-upstream/$p.res
    d="n/a"; [ -f "$old" ] && [ -f "$out/$p.res" ] && d=$(diff <(sort "$old") <(sort "$out/$p.res") | grep -c '^[<>]')
    echo "   $p rc=$rc  .res diffs vs build/out/$p-upstream: $d"
done
echo "ALL DONE"
