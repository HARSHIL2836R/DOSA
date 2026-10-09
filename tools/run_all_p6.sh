#!/usr/bin/env bash
# run_all_p6.sh - re-analyse all six benchmarks on the patch-0006 build (fix F4 of
# 02-Current-Work/02-Specs/2026-09-14-Viz-Faithfulness-Audit.md) and check each whole run against
# patch 0005: .res line multiset unchanged, .reasons and .via byte-identical. Patch 0006 only adds
# .alloc, .allocsets and .cg.
set -u
DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
CLS=$DIR/build/classes-reason6
B=$DIR/../stava/benchmarks
mkdir -p /tmp/rv/p6out /tmp/rv/p6info

bench() {   # bench <name> <cfg> <input dir> <main dirname> <prefix...>
    local name="$1" cfg="$2" indir="$3" dn="$4"; shift 4
    local out=/tmp/rv/p6out/$name-$cfg old=/tmp/rv/p5out/$name-$cfg
    echo "########## $name (MarkStoreEscaping=$cfg)"
    rm -rf "$out"; mkdir -p "$out"
    local t0=$SECONDS
    "$J/bin/java" -Xmx10g -Xss512m -cp "$SOOT:$CLS" main.Main \
        "$J" true "$indir" Harness "$out" true false "$cfg" > "$out.log" 2>&1
    local rc=$?
    echo "   stava rc=$rc  $((SECONDS-t0))s"
    grep -h "Reasons have been written\|Allocation sites have been written\|Call sites have been written\|Allocation sites not written" "$out.log" | sed 's/^/   /'
    [ $rc -eq 0 ] || return 1
    echo "   .res multiset diffs vs p5: $(diff <(sort "$old/$dn.res") <(sort "$out/$dn.res") | grep -c '^[<>]')"
    cmp -s "$old/$dn.reasons" "$out/$dn.reasons" && echo "   .reasons identical" || echo "   .reasons DIFFER"
    cmp -s "$old/$dn.via" "$out/$dn.via" && echo "   .via identical" || echo "   .via DIFFER"
    local info=/tmp/rv/p6info/$name-$cfg
    rm -rf "$info"; mkdir -p "$info"
    for p in "$@"; do cp "$out/$p"*.info "$info/" 2>/dev/null; done
    cp "$out"/*.reasons "$out"/*.via "$out"/*.alloc "$out"/*.allocsets "$out"/*.cg "$info/"
    echo "   app .info files: $(ls "$info"/*.info 2>/dev/null | wc -l)"
}

ONLY="${ONLY:-}"
want() { [ -z "$ONLY" ] || case " $ONLY " in *" $1 "*) return 0;; *) return 1;; esac; }
want avrora-false  && bench avrora  false "$B/dacapo"  dacapo  avrora.
want avrora-true   && bench avrora  true  "$B/dacapo"  dacapo  avrora.
want xalan-false   && bench xalan   false "$B/xalan"   xalan   org.apache.xalan. org.apache.xpath. org.apache.xml.
want luindex-false && bench luindex false "$B/luindex" luindex org.apache.lucene.
want fop-false     && bench fop     false "$B/fop"     fop     org.apache.fop.
want h2-false      && bench h2      false "$B/h2"      h2      org.h2.
want pmd-false     && bench pmd     false "$B/pmd"     pmd     net.sourceforge.pmd.
echo "P6 ALL DONE"
