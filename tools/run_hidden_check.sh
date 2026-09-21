H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
python3 $H/tools/hidden_reason_check.py \
  --bench "avrora:/tmp/rv/p3out/avrora:avrora." \
  --bench "xalan:/tmp/rv/p3out/xalan:org.apache.xalan." \
  --bench "luindex:/tmp/rv/p3out/luindex:org.apache.lucene." \
  --bench "fop:/tmp/rv/p3out/fop:org.apache.fop." \
  --bench "h2:/tmp/rv/p3out/h2:org.h2." \
  --bench "pmd:/tmp/rv/p3out/pmd:net.sourceforge.pmd."
