#!/bin/bash
# bci.sh — compile every corpus program and dump its bytecode offsets.
# The BCIs in each expected.md come from here; they are bytecode facts, not analysis results.
set -u
cd "$(dirname "$0")/../.."
J=/home/harshil/jvm/jdk8u502-b07

for pair in \
    E01_local_containment:E01 \
    E02_static_escape:E02 \
    E03_two_groups:E03 \
    E04_unavailable_callee:E04 \
    E05_escape_by_return:E05 \
    E06_store_into_param:E06 \
    E07_cycle:E07 \
    E08_factory_two_owners:E08 \
    M01_mixed:M01 \
    M02_interproc:M02
do
    d="${pair%%:*}"; c="${pair##*:}"
    [ -d "corpus/$d" ] || continue
    mkdir -p "build/$c"
    "$J/bin/javac" -source 8 -target 8 -d "build/$c" "corpus/$d/$c.java" 2>&1 \
        | grep -v 'bootstrap class path'
    echo "======== $c"
    "$J/bin/javap" -c -p -cp "build/$c" "$c" | grep -E 'Code:|^\s+[0-9]+: (new|putfield|putstatic|invoke|areturn)|^  [a-z].*\('
done
