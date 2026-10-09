import argparse
import sys
import os
import subprocess
import glob
import shutil

from extract.python import benchmark_scale, info_to_graph
from render.python import reason_figures, graph_to_html
from tools.python import scan_figures

DIR = os.path.dirname(os.path.abspath(__file__))
J = "/home/harshil/jvm/jdk8u502-b07"
JDK = "Temurin 8u502-b07"
SOOT = os.path.join(DIR, "../stava/soot/sootclasses-trunk-jar-with-dependencies.jar")
CLS = os.path.join(DIR, "build/classes-reason6")
B = os.path.join(DIR, "../stava/benchmarks")
os.environ["HEAPVIZ_REASON_MODE"] = "roots"

def _run_java(*args, **kwargs):
    cmd = [os.path.join(J, "bin/java")] + list(args)
    try:
        subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"Java command failed: {e}")
        sys.exit(1)

def dashboard_patch3():
    CFG = "MarkStoreEscaping=false (patch 0003: RETURNED on concrete objects)"
    os.makedirs(f"{DIR}/render/figures", exist_ok=True)
    def one(n, *prefixes):
        out = f"{DIR}/build/out/{n}-p3"
        print(f"\n########## {n}")
        benchmark_scale.main([
            "--info-dir", f"/tmp/rv/p3info/{n}",
            "--class-prefix", *prefixes,
            "--label", f"{n} (DaCapo 9.12-MR1)",
            "--jdk", JDK,
            "--config", CFG,
            "--require-reasons",
            "--out-dir", out
        ])
        reason_figures.main([
            "--graph", f"{out}/graph-full.json",
            "--title", f"{n} - {CFG}",
            "--out-prefix", f"{DIR}/render/figures/{n}-p3-reason"
        ])
        graph_to_html.main([
            "--graph", f"{out}/graph-full.json",
            "--title", f"{n} - escape explorer ({CFG})",
            "--out", f"{DIR}/render/figures/{n}-p3-explorer.html"
        ])
    
    one("avrora", "avrora.")
    one("xalan", "org.apache.xalan.", "org.apache.xpath.", "org.apache.xml.")
    one("luindex", "org.apache.lucene.")
    one("fop", "org.apache.fop.")
    one("h2", "org.h2.")
    one("pmd", "net.sourceforge.pmd.")
    
    print("\n########## artefacts")
    for f in glob.glob(f"{DIR}/render/figures/*-p3-*"):
        print(f"   {f}")

def dashboard_patch6():
    FIG = f"{DIR}/render/figures"
    print("########## move superseded figures")
    os.makedirs(f"{FIG}/stale-pre-0006", exist_ok=True)
    n_moved = 0
    for ext in ["*-reason-*.svg", "*-reason-*.dot", "*explorer*.html"]:
        for f in glob.glob(f"{FIG}/{ext}"):
            if "-p6-" not in f:
                shutil.move(f, f"{FIG}/stale-pre-0006/{os.path.basename(f)}")
                n_moved += 1
    print(f"   moved {n_moved} files")
                
    def bench(name, cfg, *prefixes):
        info = f"/tmp/rv/p6info/{name}-{cfg}"
        out = f"{DIR}/build/out/{name}-p6-{cfg}"
        conf = f"MarkStoreEscaping={cfg} (patch 0006, roots mode)"
        print(f"\n########## {name} {cfg}")
        if not os.path.exists(info):
            print(f"   MISSING {info}")
            return
        os.makedirs(out, exist_ok=True)
        benchmark_scale.main([
            "--info-dir", info,
            "--class-prefix", *prefixes,
            "--label", f"{name} (DaCapo 9.12-MR1)",
            "--jdk", JDK,
            "--config", conf,
            "--require-reasons",
            "--out-dir", out
        ])
        reason_figures.main([
            "--graph", f"{out}/graph-full.json",
            "--title", f"{name} - {conf}",
            "--out-prefix", f"{FIG}/{name}-p6-{cfg}-reason"
        ])
        graph_to_html.main([
            "--graph", f"{out}/graph-full.json",
            "--title", f"{name} - escape explorer ({conf})",
            "--out", f"{FIG}/{name}-p6-{cfg}-explorer.html"
        ])
        
    bench("avrora", "false", "avrora.")
    bench("avrora", "true", "avrora.")
    bench("xalan", "false", "org.apache.xalan.", "org.apache.xpath.", "org.apache.xml.")
    bench("luindex", "false", "org.apache.lucene.")
    bench("fop", "false", "org.apache.fop.")
    bench("h2", "false", "org.h2.")
    bench("pmd", "false", "net.sourceforge.pmd.")
    
    print("\n########## corpus")
    progs = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "M01", "M02"]
    for p in progs:
        classes = [os.path.splitext(os.path.basename(c))[0] for c in glob.glob(f"{DIR}/build/{p}/*.class")]
        if not classes:
            continue
        for cfg in ["false", "true"]:
            src = f"/tmp/rv/p6/{p}-{cfg}"
            out = f"{DIR}/build/out/{p}-p6-{cfg}"
            if not os.path.isfile(f"{src}/{p}.reasons"):
                print(f"   {p} {cfg} MISSING {src}")
                continue
            os.makedirs(out, exist_ok=True)
            conf = f"MarkStoreEscaping={cfg} (patch 0006, roots mode)"
            try:
                info_to_graph.main([
                    "--info-dir", src,
                    "--classes", *classes,
                    "--class-dir", f"{DIR}/build/{p}",
                    "--javap", f"{J}/bin/javap",
                    "--config", conf,
                    "--jdk", JDK,
                    "--definition", "S",
                    "--require-reasons",
                    "--out", f"{out}/graph.json"
                ])
                reason_figures.main([
                    "--graph", f"{out}/graph.json",
                    "--title", f"{p} ({conf})",
                    "--out-prefix", f"{FIG}/{p}-p6-{cfg}-reason"
                ])
                print(f"   {p} {cfg} ok")
            except Exception as e:
                print(f"   {p} {cfg} FAILED: {e}")
                
    print("\n########## scan: propagated reasons or placeholders DRAWN in current figures")
    scan_figures.main([FIG, "*-p6-*"])
    print("DASHBOARD DONE")

def run_all_patch6():
    os.makedirs("/tmp/rv/p6out", exist_ok=True)
    os.makedirs("/tmp/rv/p6info", exist_ok=True)
    
    def bench(name, cfg, indir, dn, *prefixes):
        out = f"/tmp/rv/p6out/{name}-{cfg}"
        old = f"/tmp/rv/p5out/{name}-{cfg}"
        print(f"########## {name} (MarkStoreEscaping={cfg})")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        
        _run_java("-Xmx10g", "-Xss512m", "-cp", f"{SOOT}:{CLS}", "main.Main",
                  J, "true", indir, "Harness", out, "true", "false", cfg)
                  
        if os.path.exists(f"{old}/{dn}.reasons") and os.path.exists(f"{out}/{dn}.reasons"):
            if open(f"{old}/{dn}.reasons", "rb").read() == open(f"{out}/{dn}.reasons", "rb").read():
                print("   .reasons identical")
            else:
                print("   .reasons DIFFER")
        if os.path.exists(f"{old}/{dn}.via") and os.path.exists(f"{out}/{dn}.via"):
            if open(f"{old}/{dn}.via", "rb").read() == open(f"{out}/{dn}.via", "rb").read():
                print("   .via identical")
            else:
                print("   .via DIFFER")
                
        info = f"/tmp/rv/p6info/{name}-{cfg}"
        shutil.rmtree(info, ignore_errors=True)
        os.makedirs(info)
        
        for p in prefixes:
            for f in glob.glob(f"{out}/{p}*.info"):
                shutil.copy(f, info)
                
        for ext in [".reasons", ".via", ".alloc", ".allocsets", ".cg"]:
            for f in glob.glob(f"{out}/*{ext}"):
                shutil.copy(f, info)
                
        print(f"   app .info files: {len(glob.glob(f'{info}/*.info'))}")
        
    bench("avrora", "false", f"{B}/dacapo", "dacapo", "avrora.")
    bench("avrora", "true", f"{B}/dacapo", "dacapo", "avrora.")
    bench("xalan", "false", f"{B}/xalan", "xalan", "org.apache.xalan.", "org.apache.xpath.", "org.apache.xml.")
    bench("luindex", "false", f"{B}/luindex", "luindex", "org.apache.lucene.")
    bench("fop", "false", f"{B}/fop", "fop", "org.apache.fop.")
    bench("h2", "false", f"{B}/h2", "h2", "org.h2.")
    bench("pmd", "false", f"{B}/pmd", "pmd", "net.sourceforge.pmd.")
    print("P6 ALL DONE")

def verify_patch6():
    W = "/tmp/rv/p6"
    os.makedirs(W, exist_ok=True)
    
    print("== compile stava-src-reason6")
    shutil.rmtree(CLS, ignore_errors=True)
    os.makedirs(CLS)
    subprocess.run([f"{J}/bin/javac", "-nowarn", "-cp", SOOT, "-sourcepath", f"{DIR}/build/stava-src-reason6", 
                    "-d", CLS, f"{DIR}/build/stava-src-reason6/main/Main.java"], check=True)
    
    if not os.path.exists(f"{CLS}/main/AllocSites.class"):
        print("COMPILE FAILED")
        sys.exit(1)
    print("   ok")
    
    progs = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "M01", "M02"]
    for cfg in ["false", "true"]:
        print(f"\n== corpus, MarkStoreEscaping={cfg}")
        for p in progs:
            old = f"/tmp/rv/p5/{p}-{cfg}"
            new = f"{W}/{p}-{cfg}"
            shutil.rmtree(new, ignore_errors=True)
            os.makedirs(new)
            
            try:
                _run_java("-Xmx6g", "-Xss512m", "-cp", f"{SOOT}:{CLS}", "main.Main",
                          J, "false", f"{DIR}/build/{p}", p, new, "true", "false", cfg)
            except Exception:
                print(f"   {p} RUN FAILED")
                continue
                
            rs = "same"
            if os.path.exists(f"{old}/{p}.reasons") and os.path.exists(f"{new}/{p}.reasons"):
                if open(f"{old}/{p}.reasons", "rb").read() != open(f"{new}/{p}.reasons", "rb").read():
                    rs = "DIFF"
            vs = "same"
            if os.path.exists(f"{old}/{p}.via") and os.path.exists(f"{new}/{p}.via"):
                if open(f"{old}/{p}.via", "rb").read() != open(f"{new}/{p}.via", "rb").read():
                    vs = "DIFF"
                    
            print(f"   {p:4s} .reasons {rs}  .via {vs}")

def main():
    parser = argparse.ArgumentParser(description="Unified Python CLI for HeapViz")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    dash_parser = subparsers.add_parser("dashboard", help="Regenerate figures and explorers")
    dash_parser.add_argument("--patch", required=True, choices=["3", "6"], help="Patch version to run dashboard for")
    
    runall_parser = subparsers.add_parser("run-all", help="Re-analyse benchmarks")
    runall_parser.add_argument("--patch", required=True, choices=["6"], help="Patch version to run")
    
    verify_parser = subparsers.add_parser("verify", help="Verify patch logic")
    verify_parser.add_argument("--patch", required=True, choices=["6"], help="Patch version to verify")
    
    args = parser.parse_args()
    
    if args.command == "dashboard":
        if args.patch == "3":
            dashboard_patch3()
        elif args.patch == "6":
            dashboard_patch6()
    elif args.command == "run-all":
        if args.patch == "6":
            run_all_patch6()
    elif args.command == "verify":
        if args.patch == "6":
            verify_patch6()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
