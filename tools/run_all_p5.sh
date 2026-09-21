#!/usr/bin/env bash
# run_all_p5.sh - re-analyse all six benchmarks on the patch-0005 build (fix F3 of
# 02-Current-Work/Viz-Faithfulness-Audit.md) and check each whole run against patch 0004:
# .res unchanged, .reasons columns 1-4 unchanged, column-5 pointer sets unchanged, own within all.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
CLS=$DIR/build/classes-reason5
B=$DIR/../stava/benchmarks
mkdir -p /tmp/rv/p5out /tmp/rv/p5info

bench() {   # bench <name> <cfg> <input dir> <main dirname> <p4 whole-run dir> <prefix...>
    local name="$1" cfg="$2" indir="$3" dn="$4" old="$5"; shift 5
    local out=/tmp/rv/p5out/$name-$cfg
    echo "########## $name (MarkStoreEscaping=$cfg)"
    rm -rf "$out"; mkdir -p "$out"
    local t0=$SECONDS
    "$J/bin/java" -Xmx10g -Xss512m -cp "$SOOT:$CLS" main.Main \
        "$J" true "$indir" Harness "$out" true false "$cfg" > "$out.log" 2>&1
    local rc=$?
    echo "   stava rc=$rc  $((SECONDS-t0))s"
    grep -h "Reasons have been written" "$out.log" | sed 's/^/   /'
    [ $rc -eq 0 ] || return 1
    echo "   .res multiset diffs vs p4: $(diff <(sort "$old/$dn.res") <(sort "$out/$dn.res") | grep -c '^[<>]')"
    printf "   "; python3 "$DIR/tools/compare_reasons_p4_p5.py" "$old" "$out" "$dn"
    local info=/tmp/rv/p5info/$name-$cfg
    rm -rf "$info"; mkdir -p "$info"
    for p in "$@"; do cp "$out/$p"*.info "$info/" 2>/dev/null; done
    cp "$out"/*.reasons "$out"/*.via "$info/"
    echo "   app .info files: $(ls "$info"/*.info 2>/dev/null | wc -l)"
}

bench avrora  false "$B/dacapo"  dacapo  /tmp/rv/out/dacapo-false-p4 avrora.
bench avrora  true  "$B/dacapo"  dacapo  /tmp/rv/out/dacapo-true-p4  avrora.
bench xalan   false "$B/xalan"   xalan   /tmp/rv/p4out/xalan-false   org.apache.xalan. org.apache.xpath. org.apache.xml.
bench luindex false "$B/luindex" luindex /tmp/rv/p4out/luindex-false org.apache.lucene.
bench fop     false "$B/fop"     fop     /tmp/rv/p4out/fop-false     org.apache.fop.
bench h2      false "$B/h2"      h2      /tmp/rv/p4out/h2-false      org.h2.
bench pmd     false "$B/pmd"     pmd     /tmp/rv/p4out/pmd-false     net.sourceforge.pmd.
echo "ALL DONE"
