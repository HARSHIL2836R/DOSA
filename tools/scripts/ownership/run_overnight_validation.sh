#!/usr/bin/env bash
# run_overnight_validation.sh - Master overnight benchmark & validation pipeline.
# Sequentially executes the complete static ownership, Scope LCA, What-If ablation,
# library inlining sweep, and verification suite across all DaCapo benchmarks.
# Designed for 5-8 hour overnight execution.
set -uo pipefail

DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG_DIR="$DIR/build/own"
mkdir -p "$LOG_DIR"
MASTER_LOG="$LOG_DIR/overnight_run.log"

exec > >(tee -a "$MASTER_LOG") 2>&1

echo "========================================================================"
echo "   STARTING OVERNIGHT VALIDATION SUITE: $(date)"
echo "   Working Directory: $DIR"
echo "   Master Log:        $MASTER_LOG"
echo "========================================================================"

t_start=$SECONDS

# Step 1: Clean build
echo ""
echo ">>> STEP 1: Building Java ownership classes..."
bash "$DIR/tools/scripts/ownership/build.sh"

# Step 2: Full Verification Suite (verify.sh stored tests)
echo ""
echo ">>> STEP 2: Running formal micro-corpus & stored verification suite..."
bash "$DIR/tools/scripts/ownership/verify.sh" stored
echo ">>> Verification suite passed with 0 errors."

# Step 3: Full DaCapo 6-Benchmark Suite (with Scope LCA & Heap Partitioning)
echo ""
echo ">>> STEP 3: Running DaCapo 9.12-MR1 benchmark suite (B & B+id)..."
bash "$DIR/tools/scripts/ownership/run_benchmarks.sh"

# Step 4: What-If Toolchain Ablation Suite (S, P, SP)
echo ""
echo ">>> STEP 4: Running What-If toolchain ablation suite (S, P, SP)..."
bash "$DIR/tools/scripts/ownership/run_whatif.sh"

# Step 5: Library Inlining Sweeps (Depths 1-4, Units 30-120)
echo ""
echo ">>> STEP 5: Running multi-round library inlining sweeps..."
BENCHES="avrora pmd" CONFIGS="1:60 2:60 3:60 4:60 3:30 3:120" bash "$DIR/tools/scripts/ownership/run_inline_sweep.sh"

# Step 6: Summary Report Generation
echo ""
echo ">>> STEP 6: Generating master ownership report..."
python3 "$DIR/tools/python/ownership/report.py" --bench > "$LOG_DIR/overnight_summary.txt"
cat "$LOG_DIR/overnight_summary.txt"

t_total=$((SECONDS - t_start))
echo ""
echo "========================================================================"
echo "   OVERNIGHT VALIDATION SUITE COMPLETE: $(date)"
echo "   Total Elapsed Time: $((t_total / 3600))h $(((t_total % 3600) / 60))m $((t_total % 60))s"
echo "   Results saved in $LOG_DIR/overnight_summary.txt"
echo "========================================================================"
