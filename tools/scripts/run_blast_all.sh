H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/DOSA
export JAVA_HOME=/home/harshil/jvm/jdk8u502-b07
cd $H/extract
run() {
  echo "########## $1"
  python3 escape_blast.py --info-dir /tmp/rv/out/$2 --class-prefix "${@:3}" \
    --label "$1 (MarkStoreEscaping=false)" --out-dir $H/build/out/$1-blast-false --top 12
}
run avrora  dacapo-false avrora.
run pmd     pmd-false    net.sourceforge.pmd.
run xalan   xalan-false  org.apache.xalan. org.apache.xpath. org.apache.xml.
