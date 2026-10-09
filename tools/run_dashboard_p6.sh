#!/usr/bin/env bash
# run_dashboard_p6.sh - regenerate every escape-reason figure and explorer from the patch-0006
# runs, in roots mode, with the own/inherited split drawn, counting application allocation sites
# (fix F4 of
# 02-Current-Work/02-Specs/2026-09-14-Viz-Faithfulness-Audit.md).
#
# Inputs: /tmp/rv/p6info/<bench>-<cfg> (run_all_p6.sh) and /tmp/rv/p6/<prog>-<cfg>
#         (verify_patch6.sh).
# Output: render/figures/<name>-p6-<cfg>-reason-*.{svg,dot}, <bench>-p6-<cfg>-explorer.html.
# The patch-0005 figures are MOVED, not deleted, to render/figures/stale-pre-0006/.
set -u
H=/mnt/c/Users/Dell/Documents/IIT_academics/BTP/heapviz
J=/home/harshil/jvm/jdk8u502-b07
JDK="Temurin 8u502-b07"
FIG=$H/render/figures
export HEAPVIZ_REASON_MODE=roots

echo "########## move superseded figures"
mkdir -p "$FIG/stale-pre-0006"
n=0
for f in "$FIG"/*-reason-*.svg "$FIG"/*-reason-*.dot "$FIG"/*explorer*.html; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in *-p6-*) continue ;; esac
    mv "$f" "$FIG/stale-pre-0006/"; n=$((n+1))
done
echo "   moved $n files"

bench() {   # bench <name> <cfg> <prefix...>
    local name="$1" cfg="$2"; shift 2
    local info=/tmp/rv/p6info/$name-$cfg out=$H/build/out/$name-p6-$cfg
    local conf="MarkStoreEscaping=$cfg (patch 0006, roots mode)"
    echo
    echo "########## $name $cfg"
    [ -d "$info" ] || { echo "   MISSING $info"; return 1; }
    cd "$H/extract"
    python3 benchmark_scale.py --info-dir "$info" --class-prefix "$@" \
        --label "$name (DaCapo 9.12-MR1)" --jdk "$JDK" --config "$conf" --require-reasons \
        --out-dir "$out" > "$out.log" 2>&1
    grep -E "^reasons:|objects \(int|fix F4|reasonCount histogram|single-reason attribution|own vs inherited|Escape with|NoEscape with" "$out.log" || true
    python3 "$H/render/reason_figures.py" --graph "$out/graph-full.json" \
        --title "$name - $conf" --out-prefix "$FIG/$name-p6-$cfg-reason" 2>&1 | grep -E "clusters drawn|n     :" || true
    python3 "$H/render/graph_to_html.py" --graph "$out/graph-full.json" \
        --title "$name - escape explorer ($conf)" \
        --out "$FIG/$name-p6-$cfg-explorer.html" 2>&1 | tail -1
}

bench avrora  false avrora.
bench avrora  true  avrora.
bench xalan   false org.apache.xalan. org.apache.xpath. org.apache.xml.
bench luindex false org.apache.lucene.
bench fop     false org.apache.fop.
bench h2      false org.h2.
bench pmd     false net.sourceforge.pmd.

echo
echo "########## corpus"
cd "$H"
for p in E01 E02 E03 E04 E05 E06 E07 E08 E09 E10 E11 M01 M02; do
    classes=$(ls "$H/build/$p"/*.class | xargs -n1 basename | sed 's/\.class$//' | tr '\n' ' ')
    for cfg in false true; do
        src=/tmp/rv/p6/$p-$cfg
        out=$H/build/out/$p-p6-$cfg
        [ -f "$src/$p.reasons" ] || { echo "   $p $cfg MISSING $src"; continue; }
        mkdir -p "$out"
        conf="MarkStoreEscaping=$cfg (patch 0006, roots mode)"
        python3 extract/info_to_graph.py --info-dir "$src" --classes $classes \
            --class-dir "$H/build/$p" --javap "$J/bin/javap" --config "$conf" --jdk "$JDK" \
            --definition S --require-reasons --out "$out/graph.json" > "$out/extract.log" 2>&1 \
            || { echo "   $p $cfg EXTRACT FAILED"; tail -3 "$out/extract.log"; continue; }
        python3 render/reason_figures.py --graph "$out/graph.json" --title "$p ($conf)" \
            --out-prefix "$FIG/$p-p6-$cfg-reason" > "$out/figures.log" 2>&1 \
            || { echo "   $p $cfg FIGURES FAILED"; tail -3 "$out/figures.log"; continue; }
        echo "   $p $cfg ok: $(grep -h 'all  :' "$out/figures.log")"
    done
done

echo
echo "########## scan: propagated reasons or placeholders DRAWN in current figures"
python3 "$H/tools/scan_figures.py" "$FIG" "*-p6-*"
echo "DASHBOARD DONE"
