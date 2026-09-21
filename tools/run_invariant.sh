H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
for p in E05 E09 E11 M01 M02; do
  python3 $H/tools/check_invariant.py /tmp/rv/p3/$p-old "$p before" /tmp/rv/p3/$p-new "$p AFTER"
done
