set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
cd $H/extract
for n in avrora xalan luindex fop h2 pmd; do
  g=$H/build/out/$n-p3/graph-full.json
  [ -f "$g" ] || { echo "   skip $n (no graph)"; continue; }
  python3 $H/render/python/graph_to_html.py --graph "$g" \
    --title "$n - escape explorer (MarkStoreEscaping=false, patch 0003)" \
    --out $H/render/figures/$n-p3-explorer.html
done
