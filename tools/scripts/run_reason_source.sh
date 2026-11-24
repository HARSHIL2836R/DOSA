H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
B=$H/../stava/benchmarks
cd $H/extract
mkdir -p $H/build/out/source-maps
run() {
  echo "##### $1"
  python3 reason_source_map.py --info-dir /tmp/rv/p3out/$1 --classes "$2/out" \
     --class-prefix "${@:3}" --label "$1 (patch 0003)" \
     --out $H/build/out/source-maps/$1-reason-source.json --top-sites 6
}
run avrora "$B/dacapo" avrora.
