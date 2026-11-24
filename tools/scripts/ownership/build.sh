#!/usr/bin/env bash
# build.sh - compile the static ownership tree (design note 2026-09-24-Ownership-Trees.md §5).
# Needs Stava's compiled classes for main.GetSootArgs, so that Soot sees exactly the arguments
# Stava gives it; build/classes-reason6 is what DOSA/build.sh produces.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
J="${JAVA_HOME_STAVA:-/home/harshil/jvm/jdk8u502-b07}"
SOOT="$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar"
OUT="$DIR/build/ownership-classes"
rm -rf "$OUT"; mkdir -p "$OUT"
"$J/bin/javac" -nowarn -cp "$SOOT:$DIR/build/classes-reason6" -d "$OUT" \
    "$DIR"/tools/java/heapviz/*.java
echo "built $OUT"
