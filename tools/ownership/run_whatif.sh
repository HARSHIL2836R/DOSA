#!/usr/bin/env bash
# run_whatif.sh - the static ownership tree on the six benchmarks, identity returns on, with the
# what-if variants (OwnershipTree.whatIf): S, Spark's special nodes keep no fields; P, phantom
# callees keep nothing; SP, both. Not sound: each measures how much of HEAP one modelling source
# accounts for. One Spark run per benchmark; the variants reuse it.
# Output: build/own/whatif/<name>/<dirname>-id.ownwhatif and .ownwhy-sp.
#
#   tools/ownership/run_whatif.sh          (detach it: setsid nohup ... & disown)
set -u
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
CP="$SOOT:$DIR/build/classes-reason6:$DIR/build/ownership-classes"
B="$DIR/../stava/benchmarks"

bench() {   # bench <name> <input dir>
    local name="$1" indir="$2" out="$DIR/build/own/whatif/$1"
    mkdir -p "$out"
    echo "########## $name"
    local t0=$SECONDS
    "$J/bin/java" -Xmx10g -Xss512m -Downership.identityReturns=true -Downership.whatif=true \
        -Downership.check=40 -cp "$CP" \
        heapviz.OwnershipTree "$J" true "$indir" Harness "$out" > "$out/run.log" 2>&1
    echo "   rc=$?  $((SECONDS-t0))s"
    grep '^\[ownership\] \(B\|S\|P\|SP\):\|CHECK FAILED' "$out/run.log" | sed 's/^/   /'
}

ONLY="${ONLY:-}"
want() { [ -z "$ONLY" ] || case " $ONLY " in *" $1 "*) return 0;; *) return 1;; esac; }
bash "$DIR/tools/ownership/build.sh"
want avrora  && bench avrora  "$B/dacapo"
want xalan   && bench xalan   "$B/xalan"
want luindex && bench luindex "$B/luindex"
want fop     && bench fop     "$B/fop"
want h2      && bench h2      "$B/h2"
want pmd     && bench pmd     "$B/pmd"
echo "WHATIF DONE"
