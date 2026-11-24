H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
cd $H/extract
python3 reason_source_map.py --info-dir /tmp/rv/p3out/avrora \
  --classes $H/../stava/benchmarks/dacapo/out --class-prefix avrora. \
  --label "avrora (patch 0003)" --only-sets $H/build/out/source-maps/common-reason-sets.json \
  --out $H/build/out/source-maps/avrora-reason-source.json --top-sites 6
