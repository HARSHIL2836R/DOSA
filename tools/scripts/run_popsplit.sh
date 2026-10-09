H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
cd $H/extract
P=population_split.py
python3 $P /tmp/rv/avrora-info-false  "avrora"  avrora.
echo
python3 $P /tmp/rv/xalan-info         "xalan"   org.apache.xalan. org.apache.xpath. org.apache.xml.
echo
python3 $P /tmp/rv/luindex-info       "luindex" org.apache.lucene.
echo
python3 $P /tmp/rv/fop-info           "fop"     org.apache.fop.
echo
python3 $P /tmp/rv/h2-info            "h2"      org.h2.
echo
python3 $P /tmp/rv/pmd-info           "pmd"     net.sourceforge.pmd.
