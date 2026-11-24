set -e
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
cd $H/extract
python3 escape_blast.py --info-dir /tmp/rv/out/dacapo-false \
  --class-prefix avrora. --label "avrora (DaCapo 9.12-MR1), MarkStoreEscaping=false" \
  --out-dir $H/build/out/avrora-blast-false --top 22 > /tmp/rv/blast-avrora.txt 2>&1
echo "blast done"
python3 bci_to_source.py --blast $H/build/out/avrora-blast-false/escape-blast.json \
  --classes /mnt/c/Users/Dell/Documents/IIT_academics/BTP/stava/benchmarks/dacapo/out \
  --top 18 --out $H/build/out/avrora-blast-false/escape-blast-sourced.json
