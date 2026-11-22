# HeapViz — Architecture & Control Flow

> **What this project does**: HeapViz implements **DOSA** (Dominator-guided Ownership for Stack Allocation), a static ownership and lifetime analysis system for Java programs.
> It runs Soot/Spark points-to analysis on DaCapo benchmarks, builds a dominator tree over the
> heap graph, and classifies every allocation site as **OWN** (owned by the allocating method),
> **UP** (owned by an ancestor in the call chain), or **HEAP** (globally reachable), with Static Scoping for static fields and Method Region Partitioning ($\mathcal{P}(M)$).

---

## 1. Directory Structure

```
heapviz/
├── build.sh              # Main build & analysis pipeline (compile → Soot → extract → render)
├── heapviz.py            # Unified Python CLI (dashboard, run-all, verify subcommands)
├── Makefile              # Make targets for corpus programs (M01, E01, etc.)
│
├── corpus/               # Micro-benchmark source files (M01, E01–E11, etc.)
│
├── patches/              # Stava source patches
│   ├── 0001-store-escape-off.patch
│   ├── 0002-escape-reasons.patch
│   ├── 0003-concrete-return-reason.patch
│   ├── 0004-successor-pointers.patch
│   ├── 0005-own-vs-inherited.patch
│   └── 0006-alloc-sites-and-call-sites.patch
│
├── extract/              # Data extraction from Soot output
│   └── python/
│       ├── info_to_graph.py       # Converts .info files → graph.json
│       ├── benchmark_scale.py     # Scales extraction for DaCapo benchmarks
│       ├── interprocedural.py     # Inter-procedural PTG stitching
│       ├── escape_blast.py        # Escape-blast analysis
│       ├── reason_source_map.py   # Maps reasons to source locations
│       ├── source_index.py        # Source file indexer
│       └── ...
│
├── render/               # Visualization generation
│   └── python/
│       ├── graph_to_svg.py        # graph.json → SVG/DOT diagrams
│       ├── graph_to_html.py       # graph.json → interactive HTML explorer
│       ├── reason_figures.py      # Escape-reason cluster/multiplicity figures
│       └── source_dashboard.py    # Source-annotated dashboards
│
├── tools/                # Analysis tools and ownership tree
│   ├── java/
│   │   └── heapviz/               # Core Java analysis engine (modularized; see §3)
│   │       ├── OwnershipTree.java       # Orchestrator & CLI entry point (~350 lines)
│   │       ├── GraphBuilder.java        # Graph B (borrow) & Graph N (naive) construction
│   │       ├── ReturnAnalysis.java      # Parameter-return summary analysis
│   │       ├── UnsafeStoreHandler.java  # sun.misc.Unsafe putObject modelling
│   │       ├── Dominators.java          # Cooper-Harvey-Kennedy dominator tree solver
│   │       ├── OwnershipGraph.java      # Edge accumulator & CSR graph representation
│   │       ├── SiteNaming.java          # Spark node & allocation site naming
│   │       ├── OutputWriter.java        # Output serialization (.own, .owntree, .ownwhy)
│   │       ├── OwnershipResult.java     # Classification result container
│   │       ├── IdentityReturns.java     # Fluent builder chain pre-rewrite
│   │       ├── LibraryInliner.java      # Small JDK allocating method inlining
│   │       └── IntList.java             # Unboxed growable int[]
│   ├── python/                    # Python analysis scripts
│   │   ├── alloc_unit.py          # Allocation-unit analysis
│   │   ├── evidence_report.py     # Evidence report generation
│   │   ├── param_hubs.py          # Parameter hub detection
│   │   ├── viz_audit.py           # Visualization audit
│   │   └── ...
│   ├── scripts/                   # Bash helper scripts
│   │   └── ownership/
│   │       ├── build.sh           # Compiles the Java ownership engine
│   │       ├── verify.sh          # Runs manual verification tests (T1–T20)
│   │       └── run_benchmarks.sh  # Runs avrora/xalan/etc. ownership benchmarks
│   ├── data/
│   │   └── known_uninstrumented.json
│   └── archive/                   # Legacy phase-specific scripts (historical)
│
├── build/                # Build outputs (compiled classes, analysis results)
│   ├── classes-reason6/           # Compiled Stava (patched with escape reasons)
│   ├── ownership-classes/         # Compiled ownership engine (OwnershipTree + friends)
│   ├── out/                       # Analysis output per program (graph.json, etc.)
│   └── own/                       # Ownership tree outputs (.own, .owntree files)
│
└── render/figures/       # Generated SVG/DOT/HTML figures
```

---

## 2. End-to-End Control Flow

### 2.1 Primary Pipeline: `make M01` / `build.sh`

This is the main flow for analyzing a single corpus program (e.g., M01):

```mermaid
flowchart TD
    A["make M01"] --> B["build.sh M01_mixed M01 ..."]

    B --> C["1. Copy Stava sources"]
    C --> C1["build/stava-src-upstream/"]
    C --> C2["build/stava-src-pye/ (patch 0001)"]
    C --> C3["build/stava-src-reason/ (patch 0002)"]

    B --> D["2. Compile Stava (javac)"]
    D --> D1["build/classes-reason/"]

    B --> E["3. Compile corpus program"]
    E --> E1["build/M01/ (*.class)"]

    B --> F["4. For each config: upstream, pye"]

    F --> G["Run Stava/Soot/Spark analysis"]
    G --> G1["build/out/M01-upstream/"]
    G --> G2["build/out/M01-pye/"]

    F --> H["extract: info_to_graph.py"]
    H --> H1["graph.json"]

    F --> I["render: graph_to_svg.py"]
    I --> I1["render/figures/*.svg, *.dot"]

    F --> J["render: reason_figures.py"]
    J --> J1["reason-clusters, multiplicity, single figures"]
```

### 2.2 Ownership Analysis Pipeline: `run_benchmarks.sh`

```mermaid
flowchart TD
    A["run_benchmarks.sh"] --> B["build.sh (compile ownership engine)"]
    B --> B1["build/ownership-classes/"]

    A --> C["For each benchmark: avrora, xalan, ..."]
    C --> D["For each config: identityReturns=false, true"]

    D --> E["java heapviz.OwnershipTree"]
    E --> E1["Soot/Spark points-to analysis"]
    E1 --> E2["Optional: IdentityReturns.rewriteAll()"]
    E2 --> E3["Optional: LibraryInliner.inlineRound()"]
    E3 --> E4["Optional: Spark re-run"]

    E4 --> F["OwnershipTree.run() (Orchestrator)"]
    F --> F1["1. number() — assign IDs to methods & sites"]
    F --> F2["2. unsafeStores.findUnsafeStores()"]
    F --> F3["3. returnAnalysis.computeReturns()"]
    F --> F4["4. methodSccs() — Tarjan SCC on call graph"]

    F --> G["Build Graph B (borrow rule)"]
    G --> G1["builder.common(gb) — root, calls, statics, heap fields"]
    G --> G2["builder.borrowFrames(gb) — new, calls, caught exceptions"]
    G --> G3["gb.freeze() → CSR format"]
    G3 --> G4["Dominators.dominators() — Cooper-Harvey-Kennedy"]
    G4 --> G5["classify(gb, 'B') — OWN / UP / HEAP per site"]
    G5 --> G6["writer.attribute(gb, b) — why each HEAP site is HEAP"]

    F --> H["Build Graph N (naive baseline)"]
    H --> H1["builder.common(gn)"]
    H --> H2["builder.naiveFrames(gn) — every local → its pts"]
    H --> H3["gn.freeze() → CSR format"]
    H3 --> H4["Dominators.dominators()"]
    H4 --> H5["classify(gn, 'N')"]

    F --> I["Output (OutputWriter)"]
    I --> I1["writer.writeOwn() → .own file"]
    I --> I2["writer.writeTree() → .owntree file"]
    I --> I3["writer.attribute() → .ownwhy file"]
```

### 2.3 Python CLI: `heapviz.py`

```mermaid
flowchart LR
    CLI["python3 heapviz.py"]
    CLI --> D["dashboard --patch 3|6"]
    CLI --> R["run-all --patch 6"]
    CLI --> V["verify --patch 6"]

    D --> D1["benchmark_scale.main()"]
    D --> D2["reason_figures.main()"]
    D --> D3["graph_to_html.main()"]
    D --> D4["scan_figures.main()"]

    R --> R1["Java Soot/Spark run per benchmark"]
    R --> R2["Copy .info/.reasons/.via to /tmp/rv/p6info/"]

    V --> V1["Compile stava-src-reason6"]
    V --> V2["Run corpus programs, compare .reasons/.via"]
```

---

## 3. Java Ownership Engine — Class Responsibilities

### Core Classes (`tools/java/heapviz/`)

`OwnershipTree.java` was modularized into a clean orchestrator (~350 lines) supported by 5 extracted single-responsibility classes:

| Class | Lines | Responsibility |
|-------|-------|---------------|
| **OwnershipTree** | ~350 | Main entry point and orchestrator. Parses Soot/Spark CLI flags, assigns node IDs (`number()`), runs Tarjan SCC analysis on call graph (`methodSccs()`, `bfsFrom()`), runs domination check verification (`classify()`), and drives the pipeline (`run()`). |
| **GraphBuilder** | ~315 | Builds graph edges: `common()` (ROOT, GLOBAL, entry points, async targets, call graph, statics, heap fields), `borrowFrames()` (Graph B borrow rule: `new`, calls returning non-parameter values, caught exceptions), and `naiveFrames()` (Graph N baseline). |
| **OutputWriter** | ~220 | Formats and writes output files: `.own` (classifications), `.owntree` (dominator chains), `.ownwhy` (HEAP attribution witness paths), prints summaries (`summary()`), and handles what-if analysis (`whatIf()`). |
| **ReturnAnalysis** | ~180 | Computes interprocedural return-parameter bitmasks (`computeReturns()`), determining whether methods return parameter-derived references or freshly allocated objects. |
| **SiteNaming** | ~150 | Translates Spark `AllocNode` objects and integer node IDs into human-readable strings (`nodeName()`, `siteName()`, `isApp()`). |
| **Dominators** | ~120 | Graph algorithms: Cooper-Harvey-Kennedy dominator tree computation (`dominators()`), BFS domination check (`dominates()`), and witness path finder (`witness()`). |
| **IdentityReturns** | ~130 | Rewrites `x = y.m()` → `y.m(); x = y` when every target returns exactly that argument. Eliminates spurious return hubs (e.g. `StringBuilder.append`). |
| **LibraryInliner** | ~220 | Copies small JDK method bodies into the application's call graph so Spark can resolve and differentiate their allocation sites. |
| **UnsafeStoreHandler** | ~95 | Detects `sun.misc.Unsafe.putObject` calls (`findUnsafeStores()`) and models them as proxy heap edges so unsafe direct memory mutations do not escape ownership tracking. |
| **OwnershipGraph** | ~70 | Edge accumulator with deduplication (`add()`). Sorts and compacts into CSR (Compressed Sparse Row) format (`freeze()`) for fast traversal. |
| **OwnershipResult** | ~20 | Data class holding classification arrays: `idom[]`, `cls[]`, `region[]`, `owner[]`, `up[]`, `rec[]`. |
| **StaticFieldLiveness** | ~260 | Implements Static Scoping: computes dominator LCA over the condensed Call Graph SCC DAG $\widetilde{G}_{\text{scc}}$ to bind global static fields to capturing method activation frames. |
| **HeapPartition** | ~180 | Implements Method Region Partitioning: groups whole-program allocation sites and static fields into method-scoped memory regions $\mathcal{P}(M)$, emitting OpenJ9 directives. |
| **IntList** | ~15 | Growable unboxed primitive `int[]` array (like `ArrayList<Integer>` without heap boxing). |

### Internal Flow of `OwnershipTree.run()`

```mermaid
flowchart TD
    subgraph "Setup"
        N["OwnershipTree.number()"] --> U["UnsafeStoreHandler.findUnsafeStores()"]
        U --> CR["ReturnAnalysis.computeReturns()"]
        CR --> SCC["OwnershipTree.methodSccs()"]
    end

    subgraph "Graph B — Borrow Rule"
        SCC --> CB["GraphBuilder.common(gb)"]
        CB --> BF["GraphBuilder.borrowFrames(gb)"]
        BF --> FB["gb.freeze() → CSR format"]
        FB --> DB["Dominators.dominators()"]
        DB --> CLB["OwnershipTree.classify(gb, 'B')"]
        CLB --> AB["OutputWriter.attribute(gb, b)"]
    end

    subgraph "Graph N — Naive Baseline"
        AB --> CN["GraphBuilder.common(gn)"]
        CN --> NF["GraphBuilder.naiveFrames(gn)"]
        NF --> FN["gn.freeze() → CSR format"]
        FN --> DN["Dominators.dominators()"]
        DN --> CLN["OwnershipTree.classify(gn, 'N')"]
    end

    subgraph "Output (OutputWriter)"
        CLN --> OWN["writer.writeOwn() → .own file"]
        CLN --> TREE["writer.writeTree() → .owntree file"]
        AB --> WHY["writer.attribute() → .ownwhy file"]
        CLN --> SUM["writer.summary() / whatIf()"]
    end
```

---

## 4. Key Concepts

### Node Numbering
Every entity in the ownership graph gets a unique integer ID:
- **0** = `ROOT` (the universe entry point)
- **1** = `GLOBAL` (static fields, special Spark nodes)
- **2 .. 2+M-1** = methods (one per reachable method in the call graph)
- **2+M .. 2+M+S-1** = allocation sites (one per `new` expression Spark tracks)
- **2+M+S ..** = Unsafe store proxy nodes

### The Argument-Passthrough Filter (Graph B vs Graph N)
- **Graph B** uses the *Argument-Passthrough Filter* (formerly borrow rule): a frame only gets an edge to an object if it actually *creates* it (`Frame-New`), receives it from a call that isn't parameter-derived (`Frame-Call`), or catches an exception (`Frame-Catch`).
- **Graph N** is the naive baseline: every local in a method points to its entire Spark points-to set, causing universal 100% constructor collapse into `GLOBAL`.
- The Argument-Passthrough Filter makes Graph B sparser and preserves method frame dominance.

### Classification & Method Region Partitioning
For each allocation site, walk up the dominator tree to the nearest method:
- **OWN**: the nearest method *is* the allocating method → the object dies when that method returns
- **UP(k)**: the nearest method is *k* SCC hops above the allocator in the call graph
- **HEAP**: no method dominates the site (reachable from GLOBAL or ROOT directly)

Together with **Static Scoping** for global static fields, allocation sites and scoped fields are partitioned into method-scoped memory regions $\mathcal{P}(M) = \mathcal{S}_{\text{OWN}}(M) \cup \bigcup_{k \ge 1} \mathcal{S}_{\text{UP}_k}(M) \cup \mathcal{F}_{\text{static}}(M)$ for OpenJ9 runtime execution.

---

## 5. Test & Verification Flow

### Quick Smoke Tests

| Command | What it tests | Time |
|---------|--------------|------|
| `./tools/scripts/ownership/build.sh` | Java compilation of the ownership engine | ~5s |
| `./tools/scripts/ownership/verify.sh T1` | Dynamic tree on a known heap (`D01.java`) | ~10s |
| `make M01` | Full pipeline on micro-benchmark M01 (compile → Soot → extract → render) | ~2 min |

### Benchmark Tests

| Command | What it tests | Time |
|---------|--------------|------|
| `ONLY="avrora" ./tools/scripts/ownership/run_benchmarks.sh` | Ownership tree on DaCapo avrora, both configs | ~4 min |
| `./tools/scripts/ownership/run_benchmarks.sh` | All 6 DaCapo benchmarks | ~30 min |

### Comprehensive Verification (`verify.sh`)

| Test | Description |
|------|-------------|
| **T1** | Dynamic tree on `D01.java`: dumps heap, checks dominator tree matches expected ownership |
| **T2** | Static tree on corpus `M01`: checks Lengauer-Tarjan = Cooper-Harvey-Kennedy |
| **T3** | Static tree on `E01`: known ground truth comparison |
| **T4–T14** | Stored-result tests: read `.own` files and check classification counts |
| **T20** | Full avrora re-run: checks output matches stored baseline (slow) |

### Expected Test Output (for regression checking)

**`verify.sh T1`** should print:
```
check: Lengauer-Tarjan and Cooper-Harvey-Kennedy differ on 0 nodes
```

**`run_benchmarks.sh` (avrora)** should print:
```
[ownership] check B: 40 application sites, 0 failures
[ownership] check N: 40 application sites, 0 failures
```

---

## 6. Data Flow Diagram

```mermaid
flowchart LR
    subgraph "Input"
        JDK["JDK 8 classes"]
        SRC["Corpus .java"]
        BENCH["DaCapo benchmarks"]
    end

    subgraph "Analysis (Java)"
        SOOT["Soot/Spark\nPoints-to Analysis"]
        OWN["OwnershipTree\n(dominator tree)"]
    end

    subgraph "Extraction (Python)"
        I2G["info_to_graph.py"]
        BSC["benchmark_scale.py"]
        IPC["interprocedural.py"]
    end

    subgraph "Rendering (Python)"
        SVG["graph_to_svg.py"]
        HTML["graph_to_html.py"]
        REAS["reason_figures.py"]
    end

    subgraph "Output"
        INFO[".info files"]
        GRAPH["graph.json"]
        FIGS["SVG/DOT figures"]
        EXPL["HTML explorers"]
        OWNF[".own / .owntree"]
    end

    JDK --> SOOT
    SRC --> SOOT
    BENCH --> SOOT

    SOOT --> INFO
    SOOT --> OWN
    OWN --> OWNF

    INFO --> I2G
    INFO --> BSC
    I2G --> GRAPH
    BSC --> GRAPH
    GRAPH --> IPC

    GRAPH --> SVG --> FIGS
    GRAPH --> HTML --> EXPL
    GRAPH --> REAS --> FIGS
```

