#!/usr/bin/env bash
# run_all_p3.sh - re-run every benchmark on the patch-0003 build, then re-extract.
#
# Patch 0003 attributes RETURNED to concrete objects, so every reason table, histogram and
# blast ranking produced before it is stale. This regenerates all of them from one build.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
CLS=$DIR/build/classes-reason3
B=$DIR/../stava/benchmarks

# name : input dir : class prefixes
run_one() {
    local name="$1"; local indir="$2"; shift 2
    local out=/tmp/rv/p3out/$name
    echo "########## $name"
    rm -rf "$out"; mkdir -p "$out"
    local t0=$SECONDS
    "$J/bin/java" -Xmx10g -Xss512m -cp "$SOOT:$CLS" main.Main \
        "$J" true "$indir" Harness "$out" true false false \
        > /tmp/rv/p3out/$name.log 2>&1
    local rc=$?
    echo "   stava rc=$rc  $((SECONDS-t0))s"
    grep -h "Reasons have been written" /tmp/rv/p3out/$name.log | sed 's/^/   /'
    [ $rc -eq 0 ] || return 1

    # app-filtered copy, same rule as every previous run
    local info=/tmp/rv/p3info/$name
    rm -rf "$info"; mkdir -p "$info"
    for p in "$@"; do cp "$out/$p"*.info "$info/" 2>/dev/null; done
    cp "$out"/*.reasons "$info/" 2>/dev/null
    echo "   app .info files: $(ls "$info"/*.info 2>/dev/null | wc -l)"
}

mkdir -p /tmp/rv/p3out /tmp/rv/p3info

run_one avrora  "$B/dacapo"  avrora.
run_one xalan   "$B/xalan"   org.apache.xalan. org.apache.xpath. org.apache.xml.
run_one luindex "$B/luindex" org.apache.lucene.
run_one fop     "$B/fop"     org.apache.fop.
run_one h2      "$B/h2"      org.h2.
run_one pmd     "$B/pmd"     net.sourceforge.pmd.

echo
echo "########## RETURNED census, all benchmarks, patch 0003"
for n in avrora xalan luindex fop h2 pmd; do
    f=$(ls /tmp/rv/p3out/$n/*.reasons 2>/dev/null | head -1)
    [ -f "$f" ] || { echo "   $n: no .reasons"; continue; }
    tot=$(grep -c RETURNED "$f")
    sets=$(grep RETURNED "$f" | cut -f4 | sort -u | wc -l)
    types=$(grep RETURNED "$f" | cut -f3 | sort -u | tr '\n' ' ')
    printf "   %-8s %6d objects, %3d distinct reason sets, types: %s\n" "$n" "$tot" "$sets" "$types"
done
