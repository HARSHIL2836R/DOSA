# heapviz

Micro-corpus and static visualisation of Stava's escape-dependency graph.

New code only. `../stava/` and `../Region-Based-Object-Allocation-in-Java/` are **reference
checkouts and are never edited**. Anything Stava would have to change to emit what we need
lives in `patches/` as an unapplied `.patch` file, applied only to a throwaway copy of the
source under `build/`.

## Layout

| path | what |
|---|---|
| `corpus/E<nn>_<name>/` | one micro-program (`.java`) plus `expected.md`, the hand-derivation written **before** the run |
| `extract/` | `.info` → `graph.json` |
| `render/` | `graph.json` → `.dot` → `.svg` / `.png` |
| `patches/` | changes Stava would need; never applied in place |
| `patches/0002-escape-reasons.patch` | the Phase 11 instrumentation: per-object escape reasons in a side map, and `MarkStoreEscaping` on argv[7] |
| `patches/0003-concrete-return-reason.patch` | `RETURNED` recorded on the concrete returned object, not the synthetic return slot |
| `patches/0004-successor-pointers.patch` | Phase 13: the successor each propagated reason fired through, as a `GROUP` column plus `<dirname>.via`; `read_reasons` resolves them to causes by default (`HEAPVIZ_REASON_MODE=raw` to disable) |
| `tools/viz_audit.py` | Phase 14: checks the reason figures against `02-Current-Work/Viz-Faithfulness-Audit.md` (`--mode roots` for figures built on patch 0004) |
| `tools/run_all_p4.sh`, `tools/run_dashboard_p4.sh` | Phase 15: re-analyse every benchmark and corpus program on patch 0004, then rebuild every reason figure and explorer in roots mode |
| `tools/scan_figures.py` | Phase 15: fails if a figure draws a propagated reason or a caption placeholder (reads drawn data, not captions) |
| `patches/0005-own-vs-inherited.patch` | Phase 16: per object, which reasons fired on it (OWN, column 6) and which its resolver component stamped on it; own successor pointers (column 7) |
| `tools/verify_patch5.sh`, `tools/run_all_p5.sh`, `tools/compare_reasons_p4_p5.py` | Phase 16: patch 0005 changes nothing but the two new columns (corpus, both configurations; six benchmarks) |
| `tools/own_witness.py` | Phase 16: an own MONITOR/THROWN/STATIC_FIELD_*/CONSTANT_OBJECT must have its opcode in the object's method |
| `tools/param_hubs.py`, `tools/run_param_hubs.sh` | Phase 16: allocation sites escaping through a parameter, parameter hubs, hoist candidates (02-Current-Work/Param-Escape-Hubs-Report.md) |
| `tools/run_dashboard_p5.sh` | Phase 16: rebuild every reason figure and explorer with the own/inherited split drawn |
| `render/figures/*-p5-*` | the current reason figures and explorers; `stale-pre-0005/` and `stale-pre-0004/` hold the superseded ones |
| `render/reason_figures.py` | the three escape-reason figures (clusters, multiplicity, single-reason attribution) |
| `build/` | throwaway: compiled corpus classes, compiled Stava classes, run output |
| `Makefile` | `make E01` = compile, analyse, extract, render one program |

## Running record

`../02-Current-Work/Micro-Corpus-Log.md` — every phase, command, and failure, append-only.

## Conventions

- Every figure caption states the JDK build string, the include/exclude filter, the
  equi-escape definition (S or C), and what the colours mean.
- Colour means **equi-escape set membership and nothing else** in every PTG figure. Edge style
  means provenance. The reason figures added in Phase 11 do not draw equi-escape sets at all,
  so colour there means reason count / real-vs-surrender, and each of them says so in its own
  legend. Two encodings are never on screen at once.
- No number in this repo is quoted without the filter it was measured under.
- An escape *reason* is only as good as the instrumentation that records it: a firing site that
  was never instrumented is invisible, and `isSurrender()` is the only thing separating "the
  program escapes" from "Stava gave up".
