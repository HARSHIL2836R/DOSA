for n in xalan luindex fop pmd; do
  echo "=== $n"
  grep 'Error at:' /tmp/rv/p3out/$n.log 2>/dev/null | sed 's/.* of //' | head -5
done
