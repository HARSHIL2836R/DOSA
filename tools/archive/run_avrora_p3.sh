DIR=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
SOOT=$DIR/../stava/soot/sootclasses-trunk-jar-with-dependencies.jar
OUT=/tmp/rv/out/dacapo-false-p3
rm -rf "$OUT"; mkdir -p "$OUT"
$J/bin/java -Xmx10g -Xss512m -cp "$SOOT:$DIR/build/classes-reason3" main.Main \
   "$J" true "$DIR/../stava/benchmarks/dacapo" Harness "$OUT" true false false \
   > /tmp/rv/avrora-p3.log 2>&1
echo "rc=$?"
grep "Reasons have been written" /tmp/rv/avrora-p3.log
A=/tmp/rv/out/dacapo-false; B=$OUT
echo "== constraint 1: .res multiset"
echo "   old $(grep -c '' $A/dacapo.res) new $(grep -c '' $B/dacapo.res)  diffs $(diff <(sort $A/dacapo.res) <(sort $B/dacapo.res) | grep -c '^[<>]')"
echo "== RETURNED by objectType"
grep RETURNED $B/dacapo.reasons | cut -f3 | sort | uniq -c | sed 's/^/   /'
echo "== distinct reason sets containing RETURNED: $(grep RETURNED $B/dacapo.reasons | cut -f4 | sort -u | wc -l)"
echo "== app-only RETURNED: $(grep RETURNED $B/dacapo.reasons | grep -c '^<avrora\.')"
echo "== THE DISCRIMINATING CHECK"
python3 $DIR/tools/python/check_invariant.py $A "avrora before" $B "avrora AFTER"
