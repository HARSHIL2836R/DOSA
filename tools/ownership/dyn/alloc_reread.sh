#!/usr/bin/env bash
# alloc_reread.sh - re-read the Flight Recorder recordings alloc_profile.sh left in /tmp/dyn/<b>-jfr/
# with the current AllocWeights (which records four caller frames for library inlining), without
# running the benchmarks again. Output: build/own/dyn/<b>/alloc.tsv.
#
#   tools/ownership/dyn/alloc_reread.sh [bench ...]      default: all six
set -u
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
C=/tmp/dyn/awcls
rm -rf "$C"; mkdir -p "$C"
"$J/bin/javac" -nowarn -cp "$J/jre/lib/jfr.jar" -d "$C" "$DIR/tools/ownership/dyn/AllocWeights.java"
bs=("$@"); [ ${#bs[@]} -eq 0 ] && bs=(avrora xalan luindex fop h2 pmd)
for b in "${bs[@]}"; do
    f=/tmp/dyn/$b-jfr/alloc.jfr
    [ -f "$f" ] || { echo "$b: no recording at $f (run alloc_profile.sh)"; continue; }
    echo -n "$b: "
    "$J/bin/java" -Xmx2g -cp "$J/jre/lib/jfr.jar:$C" AllocWeights "$f" "$DIR/build/own/dyn/$b/alloc.tsv"
done
