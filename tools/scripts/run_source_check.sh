#!/usr/bin/env bash
# run_source_check.sh - tools/python/source_check.py on all six benchmarks (patch-0006 runs), in parallel.
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
chk() { python3 $H/tools/python/source_check.py --bench $1 --alloc $(ls /tmp/rv/p6info/$1-false/*.alloc) --class-prefix "${@:2}" > /tmp/rv/sc-$1.txt 2>&1; }
chk avrora avrora. &
chk xalan org.apache.xalan. org.apache.xpath. org.apache.xml. &
chk luindex org.apache.lucene. &
chk fop org.apache.fop. &
chk h2 org.h2. &
chk pmd net.sourceforge.pmd. &
wait
cat /tmp/rv/sc-avrora.txt /tmp/rv/sc-xalan.txt /tmp/rv/sc-luindex.txt /tmp/rv/sc-fop.txt /tmp/rv/sc-h2.txt /tmp/rv/sc-pmd.txt
