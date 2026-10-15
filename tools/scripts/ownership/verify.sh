#!/usr/bin/env bash
# verify.sh - the manual tests of 02-Current-Work/02-Specs/2026-10-02-Ownership-Verification.md.
# Each test prints what it finds; the note gives the output to compare against. Nothing here
# decides pass or fail.
#
#   bash tools/scripts/ownership/verify.sh T1          one test
#   bash tools/scripts/ownership/verify.sh list        the tests and what each costs
#   bash tools/scripts/ownership/verify.sh stored      T4 to T14, one after the other
#
# Tests T1-T3 run code; T4-T15 read results already on disk; T20 re-runs avrora (slow).
set -u
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
CP="$SOOT:$DIR/build/classes-reason6:$DIR/build/ownership-classes"
OWN="$DIR/build/own"
cd "$DIR"

app_sites() {   # app_sites <file.own>: site, class, levels up, region
    awk -F'\t' '$2==1 {r=$4; sub(/^<[^:]*: /,"",r); sub(/>$/,"",r); print "   " $1 "  " $3 "  up=" $6 "  region=" r}' "$1"
}

tool() {        # tool <corpus dir> <MAIN> <java properties...>: compile into build/verify, run, leave output there
    local src="$1" main="$2"; shift 2
    local cls="$DIR/build/verify/$main" out="$OWN/verify/$main"
    rm -rf "$cls" "$out"; mkdir -p "$cls" "$out"
    "$J/bin/javac" -source 8 -target 8 -d "$cls" "$DIR/corpus/$src"/*.java 2>&1 | grep -v 'bootstrap class path'
    "$J/bin/java" -Xmx3g "$@" -Downership.check=1000 -cp "$CP" heapviz.OwnershipTree "$J" false "$cls" "$main" "$out" \
        > "$out/run.log" 2>&1
}

case "${1:-list}" in
list)
    grep -E '^(T[0-9]+|stored)\)|^    # ' "$0" | sed 's/^    # /      /'
    ;;

stored)
    # T4 to T14 in order, each under its own heading; reads stored results only (4-5 min)
    for t in T4 T5 T6 T7 T8 T9 T10 T11 T12 T13 T14; do echo "==== $t"; bash "$0" $t; done
    ;;

T1)
    # the dynamic tree on a known heap: D01 dumps its own heap two frames deep (10 s)
    W=/tmp/verify; rm -rf $W; mkdir -p $W/cls
    "$J/bin/javac" -d $W/cls tools/java/ownership/dyn/test/D01.java
    ( cd $W && "$J/bin/java" -Xmx64m -cp $W/cls D01 $W/d01.hprof > /dev/null )
    python3 tools/python/ownership/dyn/hprof_tree.py $W/d01.hprof --check-chk --show Box Item Holder \
        | grep -E '^check|^   (Box|Item|Holder)#' \
        | sed -E 's/#[0-9a-f]+//g; s/frame t[0-9]+ d[0-9]+ /frame /g; s/thread [0-9]+/thread/; s/on 0 of [0-9]+ nodes/on 0 nodes/' \
        | sort
    ;;

T2)
    # the static tool, live, on O01: graph B, then with identity returns (2-4 min)
    tool O01_frame_tree O01 -Downership.identityReturns=false
    echo "B:";     app_sites "$OWN/verify/O01/O01.own";    grep -h 'check B' "$OWN/verify/O01/run.log" | sed 's/^/   /'
    tool O01_frame_tree O01 -Downership.identityReturns=true
    echo "B + identity returns:"; app_sites "$OWN/verify/O01/O01-id.own"; grep -h 'check B' "$OWN/verify/O01/run.log" | sed 's/^/   /'
    ;;

T3)
    # library inlining, live, on O07: the two copies of LinkedList's iterator (2-4 min)
    tool O07_library_context O07 -Downership.identityReturns=true -Downership.inlineLib=true
    awk -F'\t' '$2==1 && /ListItr\t/ {print "   " $1 "  " $3}' "$OWN/verify/O07/O07-id-inl.own"
    awk -F'\t' '$2==1 && /^<O07[^#]*\|/ {print "   " $1 "  " $3}' "$OWN/verify/O07/O07-id-inl.own"
    grep -h 'inlining, round\|reachability check\|check B' "$OWN/verify/O07/run.log" | sed 's/^\[ownership\] /   /'
    ;;

T4)
    # the stored corpus results for O01-O09, one site per line (instant)
    for p in O01 O02 O03 O04 O05 O06 O07 O08 O09; do
        echo "$p, B:";                     app_sites "$OWN/$p/$p.own"
        echo "$p, B + identity returns:";  app_sites "$OWN/$p/$p-id.own"
    done
    ;;

T5)
    # corpus against Stava's verdicts, and the borrow-rule ablation (instant)
    python3 tools/python/ownership/corpus_vs_stava.py | tail -8
    ;;

T6)
    # every run's self-check: the claimed immediate dominator really dominates (instant)
    for g in "corpus:$OWN/[EMO][0-9][0-9]/run-*.log" "benchmarks:$OWN/bench/*/run-*.log" "inlining:$OWN/inline/*/run.log" \
             "what-if:$OWN/whatif/*/run.log" "sweep:$OWN/sweep/*/run.log"; do
        name=${g%%:*}; pat=${g#*:}
        echo "$name: $(cat $pat | grep -c 'check B: .* 0 failures') runs passed, $(cat $pat | grep -c 'CHECK FAILED') failures"
    done
    ;;

T7)
    # site counts on six benchmarks, Micro-Corpus-Log F20.4 (20 s)
    python3 tools/python/ownership/report.py --bench --brief
    ;;

T8)
    # byte shares on six benchmarks, F20.5 and F21.6 (1-2 min)
    for b in avrora xalan luindex fop h2 pmd; do python3 tools/python/ownership/dyn/alloc_weight.py --bench $b --brief; done
    ;;

T9)
    # the sweep of the inliner's limits, F21.7 (1-2 min)
    for b in avrora pmd; do for c in d1-u60 d2-u60 d3-u60 d4-u60 d3-u30 d3-u120; do
        echo "$b $c: $(python3 tools/python/ownership/dyn/alloc_weight.py --bench $b --brief --inline-dir build/own/sweep/$b-$c \
            | grep -o 'all bytes OWN+UP:[^(]*')"
    done; done
    ;;

T10)
    # the what-if runs, F21.1 (10 s)
    python3 tools/python/ownership/report.py --whatif
    ;;

T11)
    # the inliner's reachability check, every inlining run (instant)
    for f in "$OWN"/inline/*/run.log "$OWN"/sweep/*/run.log; do
        d=$(basename "$(dirname "$f")")
        echo "$d: $(grep -h 'reachability check' "$f" | sed 's/.*check: //; s/ reachable before.*//')"
    done
    ;;

T12)
    # the live-heap snapshots, first dump of each benchmark, F20.6 (instant)
    for b in avrora xalan luindex fop h2 pmd; do
        sed -n '1,3p' "$OWN/dyn/$b/dump-1.txt" | sed 's|/tmp/dyn/||; s/^   /      /'
    done
    ;;

T13)
    # bytecode offsets: the call Flight Recorder and the inliner must agree on (instant)
    ( cd "$DIR/../stava/benchmarks/dacapo/out" && "$J/bin/javap" -c -p 'avrora/sim/radio/Medium$Receiver.class' ) \
        | sed -n '/earliestNewTransmission(long)/,/astore        5/p' | tail -2
    grep 'earliestNewTransmission' "$OWN/inline/avrora/dacapo-id-inl.own" | grep 'ListItr' | cut -f1,3 \
        | sed 's/<avrora.sim.radio.Medium$Receiver: avrora.sim.radio.Medium$Transmission //'
    grep -P '^java.util.LinkedList\tlistIterator' "$OWN/dyn/avrora/alloc.tsv" | sort -t$'\t' -k5 -rn | head -1 \
        | cut -f4,5,7 | cut -c1-230
    ;;

T14)
    # the heaviest site, counted without my scripts: avrora's LinkedList iterators (instant)
    awk -F'\t' '!/^#/ {t+=$5} $1=="java.util.LinkedList" && $2=="listIterator" {i+=$5}
                END {printf "LinkedList.listIterator: %d of %d sampled bytes = %.1f %%\n", i, t, 100*i/t}' "$OWN/dyn/avrora/alloc.tsv"
    head -1 "$OWN/dyn/avrora/alloc.tsv"
    ;;

T15)
    # one hand check, to read: h2's Message.translate and getSQLException (instant)
    sed -n '79,106p' build/sources/h2/h2database-aa85b3545f99a8aae5ce022ecc2e5788f9e8bb52/h2/src/main/org/h2/message/Message.java
    ;;

T16)
    # five snapshots recomputed from the kept heap dumps; h2's 5 million objects are left out (1 min)
    for b in avrora xalan luindex fop pmd; do
        if [ -f /tmp/dyn/$b/dump-1.hprof ]; then
            python3 tools/python/ownership/dyn/hprof_tree.py /tmp/dyn/$b/dump-1.hprof | sed -n '1,3p' | sed 's|/tmp/dyn/||; s/^   /      /'
        else
            echo "$b: /tmp/dyn/$b/dump-1.hprof is gone; make it again with tools/scripts/ownership/snapshot_run.sh $b"
        fi
    done
    ;;

T20)
    # re-run avrora from scratch: Spark, both variants, then library inlining (5-20 min)
    # the results it replaces are copied to build/own/verify/before-T20 first
    rm -rf "$OWN/verify/before-T20"; mkdir -p "$OWN/verify/before-T20"
    cp -r "$OWN/bench/avrora" "$OWN/verify/before-T20/bench-avrora"
    cp -r "$OWN/inline/avrora" "$OWN/verify/before-T20/inline-avrora"
    ONLY=avrora bash tools/scripts/ownership/run_benchmarks.sh | grep -E 'rc=|\] B:'
    ONLY=avrora bash tools/scripts/ownership/run_inline.sh | grep -E 'rc=|\] B:'
    grep -h 'reachability check' "$OWN/inline/avrora/run.log" | sed 's/.*check: /   reachability: /'
    python3 tools/python/ownership/report.py --bench --brief --only avrora
    python3 tools/python/ownership/dyn/alloc_weight.py --bench avrora --brief
    for f in bench/avrora/dacapo.own bench/avrora/dacapo-id.own inline/avrora/dacapo-id-inl.own; do
        old="$OWN/verify/before-T20/$(echo $f | sed 's|/avrora/|-avrora/|')"
        if cmp -s <(sort "$OWN/$f") <(sort "$old"); then echo "$f: identical to the stored result"
        else echo "$f: differs from the stored result on $(diff <(sort "$OWN/$f") <(sort "$old") | grep -c '^[<>]') lines"; fi
    done
    ;;

T17)
    # Scope LCA on O08: scoped static cache
    tool O08_static_scoped O08 -Downership.scopeLca=false
    echo "O08 without Scope LCA (legacy):"
    app_sites "$OWN/verify/O08/O08.own"
    tool O08_static_scoped O08 -Downership.scopeLca=true
    echo "O08 with Scope LCA:"
    app_sites "$OWN/verify/O08/O08.own"
    grep -h 'static field liveness\|check B' "$OWN/verify/O08/run.log" | sed 's/^/   /'
    ;;

T18)
    # Scope LCA on O09: cross-frame static session under controller
    tool O09_static_cross_frame O09 -Downership.scopeLca=false
    echo "O09 without Scope LCA (legacy):"
    app_sites "$OWN/verify/O09/O09.own"
    tool O09_static_cross_frame O09 -Downership.scopeLca=true
    echo "O09 with Scope LCA:"
    app_sites "$OWN/verify/O09/O09.own"
    grep -h 'static field liveness\|check B' "$OWN/verify/O09/run.log" | sed 's/^/   /'
    ;;

*)
    echo "unknown test $1; try: bash tools/scripts/ownership/verify.sh list"
    ;;
esac
