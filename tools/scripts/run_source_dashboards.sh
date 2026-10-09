set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
B=$H/../stava/benchmarks
O=$H/build/out/source-maps
cd $H/extract
go() {
  echo "##### $1"
  python3 reason_source_map.py --info-dir /tmp/rv/p3out/$1 --classes "$2/out" \
    --class-prefix "${@:3}" --label "$1 (patch 0003)" \
    --only-sets "$O/common-reason-sets.json" \
    --out "$O/$1-reason-source.json" --top-sites 3 2>&1 | tail -3
  python3 $H/render/python/source_dashboard.py --map "$O/$1-reason-source.json" \
    --classes "$2/out" --out "$H/render/figures/$1-source-dashboard.html" \
    --sites-per-reason 15
}
go avrora  "$B/dacapo"  avrora.
go xalan   "$B/xalan"   org.apache.xalan. org.apache.xpath. org.apache.xml.
go luindex "$B/luindex" org.apache.lucene.
go fop     "$B/fop"     org.apache.fop.
go h2      "$B/h2"      org.h2.
go pmd     "$B/pmd"     net.sourceforge.pmd.
