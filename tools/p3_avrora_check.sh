A=/tmp/rv/out/dacapo-false
B=/tmp/rv/out/dacapo-false-p3
echo "== constraint 1: .res line multiset"
for f in $A/*.res; do n=$(basename $f); done
ls $A/*.res $B/*.res 2>/dev/null | head -4
o=$(ls $A/*.res 2>/dev/null | head -1); p=$(ls $B/*.res 2>/dev/null | head -1)
if [ -n "$o" ] && [ -n "$p" ]; then
  echo "   old $(grep -c '' $o) lines, new $(grep -c '' $p) lines"
  echo "   multiset diffs: $(diff <(sort $o) <(sort $p) | grep -c '^[<>]')"
else
  echo "   NO .res FOUND"
fi
echo
echo "== RETURNED by objectType (whole run)"
for d in $A $B; do
  echo "   $(basename $d):"
  grep RETURNED $d/dacapo.reasons | cut -f3 | sort | uniq -c | sed 's/^/     /'
done
echo
echo "== application only (avrora.*)"
for d in $A $B; do
  echo -n "   $(basename $d): "
  grep RETURNED $d/dacapo.reasons | grep -c '^<avrora\.'
done
echo
echo "== reason sets containing RETURNED, after (top 8, app only)"
grep RETURNED $B/dacapo.reasons | grep '^<avrora\.' | cut -f4 | sort | uniq -c | sort -rn | head -8
echo
echo "== objects with >=1 reason"
for d in $A $B; do
  echo -n "   $(basename $d): "
  awk -F'\t' '$4!=""' $d/dacapo.reasons | wc -l
done
