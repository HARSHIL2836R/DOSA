#!/usr/bin/env bash
# run_source_maps.sh - universal reason sets across all six benchmarks, then map only those
# objects to (allocation site, escape site).
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
B=$H/../stava/benchmarks
O=$H/build/out/source-maps
mkdir -p "$O"
cd "$H/extract"

echo "########## universal reason sets"
python3 common_reason_sets.py --out "$O/common-reason-sets.json" \
  --bench "avrora:/tmp/rv/p3out/avrora:avrora." \
  --bench "xalan:/tmp/rv/p3out/xalan:org.apache.xalan.,org.apache.xpath.,org.apache.xml." \
  --bench "luindex:/tmp/rv/p3out/luindex:org.apache.lucene." \
  --bench "fop:/tmp/rv/p3out/fop:org.apache.fop." \
  --bench "h2:/tmp/rv/p3out/h2:org.h2." \
  --bench "pmd:/tmp/rv/p3out/pmd:net.sourceforge.pmd."

map() {  # map <name> <benchdir> <prefix...>
  echo
  echo "########## $1 — alloc + escape sites, universal sets only"
  python3 reason_source_map.py --info-dir "/tmp/rv/p3out/$1" --classes "$2/out" \
    --class-prefix "${@:3}" --label "$1 (patch 0003)" \
    --only-sets "$O/common-reason-sets.json" \
    --out "$O/$1-reason-source.json" --top-sites 6
}

map avrora  "$B/dacapo"  avrora.
map xalan   "$B/xalan"   org.apache.xalan. org.apache.xpath. org.apache.xml.
map luindex "$B/luindex" org.apache.lucene.
map fop     "$B/fop"     org.apache.fop.
map h2      "$B/h2"      org.h2.
map pmd     "$B/pmd"     net.sourceforge.pmd.
