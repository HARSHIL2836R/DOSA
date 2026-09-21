for n in avrora xalan luindex fop h2 pmd; do
  f=/tmp/rv/p3out/$n.log
  a=$(grep -c 'Error at:' "$f" 2>/dev/null)
  b=$(grep -c 'IllegalBCIException' "$f" 2>/dev/null)
  printf "  %-8s 'Error at:' %-6s IllegalBCIException %-6s\n" "$n" "$a" "$b"
done
