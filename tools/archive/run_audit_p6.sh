#!/usr/bin/env bash
# run_audit_p6.sh - tools/python/viz_audit.py O5 on every patch-0006 reason figure set, in the unit they
# are drawn in (application allocation sites, alias rule HEAPVIZ_ALIAS_REASONS, default own).
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
export HEAPVIZ_REASON_MODE=roots
au() {   # au <name> <cfg> <prefix...>
    local n="$1" c="$2"; shift 2
    python3 $H/tools/python/viz_audit.py --info-dir /tmp/rv/p6info/$n-$c --class-prefix "$@" --label "$n $c" \
        --figures $H/render/figures/$n-p6-$c-reason --mode roots 2>/dev/null | sed -n '1,/-- O3/p' | grep -v "^$\|-- O3"
}
au avrora false avrora.
au avrora true avrora.
au xalan false org.apache.xalan. org.apache.xpath. org.apache.xml.
au luindex false org.apache.lucene.
au fop false org.apache.fop.
au h2 false org.h2.
au pmd false net.sourceforge.pmd.
echo "AUDIT DONE"
