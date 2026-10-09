#!/usr/bin/env bash
# run_benchmarks.sh - the static ownership tree on the six DaCapo 9.12-MR1 benchmarks, with and
# without identity returns. Same Soot arguments as tools/run_all_p6.sh (main.GetSootArgs,
# Tamiflex log), plus merge-stringbuffer:false. Output: build/own/bench/<name>/.
#
#   tools/ownership/run_benchmarks.sh                  all six, one after another
#   ONLY="avrora h2" tools/ownership/run_benchmarks.sh
#
# Expect 3-10 minutes per benchmark per configuration. A run is finished when its
# run-<id>.log ends with two "[ownership] B:" / "N:" summary lines; a log that stops earlier,
# with no Java exception, was killed from outside, not failed.
set -u
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
CP="$SOOT:$DIR/build/classes-reason6:$DIR/build/ownership-classes"
B="$DIR/../stava/benchmarks"

bench() {   # bench <name> <input dir>
    local name="$1" indir="$2" out="$DIR/build/own/bench/$1"
    mkdir -p "$out"
    for id in false true; do
        echo "########## $name identityReturns=$id"
        local t0=$SECONDS
        "$J/bin/java" -Xmx10g -Xss512m -Downership.identityReturns=$id -Downership.check=40 -cp "$CP" \
            heapviz.OwnershipTree "$J" true "$indir" Harness "$out" > "$out/run-$id.log" 2>&1
        echo "   rc=$?  $((SECONDS-t0))s"
        grep '^\[ownership\]' "$out/run-$id.log" | grep -v 'soot args\|async targets' | sed 's/^/   /'
    done
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
echo "OWNERSHIP BENCHMARKS DONE"
