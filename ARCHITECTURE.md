# HeapViz — Architecture & Control Flow

> **What this project does**: HeapViz is a static ownership analysis tool for Java programs.
> It runs Soot/Spark points-to analysis on DaCapo benchmarks, builds a dominator tree over the
> heap graph, and classifies every allocation site as **OWN** (owned by the allocating method),
> **UP** (owned by an ancestor in the call chain), or **HEAP** (globally reachable).

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
│   └── 0002-escape-reasons.patch
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
│   │   └── heapviz/               # Core Java analysis engine (see §3)
│   │       ├── OwnershipTree.java
│   │       ├── OwnershipGraph.java
│   │       ├── Dominators.java
│   │       ├── OwnershipResult.java
│   │       ├── IntList.java
│   │       ├── IdentityReturns.java
│   │       └── LibraryInliner.java
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

    E4 --> F["OwnershipTree.run()"]
    F --> F1["1. number() — assign IDs to methods & sites"]
    F --> F2["2. findUnsafeStores()"]
    F --> F3["3. computeReturns() — return-parameter analysis"]
    F --> F4["4. methodSccs() — Tarjan SCC on call graph"]

    F --> G["Build Graph B (borrow rule)"]
    G --> G1["common() — root, calls, statics, heap fields"]
    G --> G2["borrowFrames() — new, calls, caught exceptions"]
    G --> G3["freeze() → CSR format"]
    G3 --> G4["Dominators.dominators() — Cooper-Harvey-Kennedy"]
    G4 --> G5["classify() — OWN / UP / HEAP per site"]
    G5 --> G6["attribute() — why each HEAP site is HEAP"]

    F --> H["Build Graph N (naive baseline)"]
    H --> H1["common()"]
    H --> H2["naiveFrames() — every local → its pts"]
    H --> H3["classify()"]

    F --> I["Output"]
    I --> I1[".own file (one line per site)"]
    I --> I2[".owntree file (dominator chains)"]
    I --> I3[".ownwhy file (HEAP attribution)"]
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

| Class | Lines | Responsibility |
|-------|-------|---------------|
| **OwnershipTree** | ~1050 | Main entry point and orchestrator. Runs Soot, numbers nodes, builds graphs, classifies sites, writes output. |
| **OwnershipGraph** | ~70 | Edge accumulator with deduplication. Freezes into CSR (Compressed Sparse Row) format for fast traversal. |
| **Dominators** | ~120 | Graph algorithms: Cooper-Harvey-Kennedy dominator tree, BFS domination check, witness path finder. |
| **OwnershipResult** | ~18 | Data class holding classification results: `idom[]`, `cls[]`, `region[]`, `owner[]`, `up[]`, `rec[]`. |
| **IntList** | ~12 | Growable `int[]` (like `ArrayList<Integer>` without boxing). |
| **IdentityReturns** | ~130 | Rewrites `x = y.m()` → `y.m(); x = y` when every target returns exactly that argument. Reduces graph noise. |
| **LibraryInliner** | ~220 | Copies JDK method bodies into the application's call graph so Spark can resolve their allocations. |

### Internal Flow of `OwnershipTree.run()`

```mermaid
flowchart TD
    subgraph "Setup"
        N["number()"] --> U["findUnsafeStores()"]
        U --> CR["computeReturns()"]
        CR --> SCC["methodSccs()"]
    end

    subgraph "Graph B — Borrow Rule"
        SCC --> CB["common(gb)"]
        CB --> BF["borrowFrames(gb)"]
        BF --> FB["gb.freeze()"]
        FB --> DB["Dominators.dominators()"]
        DB --> CLB["classify(gb, 'B')"]
        CLB --> AB["attribute(gb, b)"]
    end

    subgraph "Graph N — Naive Baseline"
        AB --> CN["common(gn)"]
        CN --> NF["naiveFrames(gn)"]
        NF --> FN["gn.freeze()"]
        FN --> DN["Dominators.dominators()"]
        DN --> CLN["classify(gn, 'N')"]
    end

    subgraph "Output"
        CLN --> OWN[".own file"]
        CLN --> TREE[".owntree file"]
        AB --> WHY[".ownwhy file"]
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

### The Borrow Rule (Graph B vs Graph N)
- **Graph B** uses the *borrow rule*: a frame only gets an edge to an object if it actually *creates* it (`new`), receives it from a call that isn't parameter-derived, or catches it.
- **Graph N** is the naive baseline: every local in a method points to its entire Spark points-to set.
- The borrow rule makes Graph B much sparser, letting more sites be classified as OWN.

### Classification
For each allocation site, walk up the dominator tree to the nearest method:
- **OWN**: the nearest method *is* the allocating method → the object dies when that method returns
- **UP(k)**: the nearest method is *k* SCC hops above the allocator in the call graph
- **HEAP**: no method dominates the site (reachable from GLOBAL or ROOT directly)

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

