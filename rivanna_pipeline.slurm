#!/bin/bash
#SBATCH --job-name=rgc-pipeline
#SBATCH --account=spinquest_standard
#SBATCH --partition=standard
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=logs/slurm-%A_%a.out
#SBATCH --error=logs/slurm-%A_%a.err
#
# generate -> simulate -> reconstruct -> ROOT, one SLURM job. See CLAUDE.md.
#
# Usage:
#   sbatch rivanna_pipeline.slurm                       # sidis, defaults
#   PHYSICS=jpsi sbatch rivanna_pipeline.slurm
#   sbatch --array=0-9 rivanna_pipeline.slurm            # unique seeds/dirs
#   NEVENTS=5000 GCARD=rgc_fall2022.gcard sbatch rivanna_pipeline.slurm
#
# New channel: add configs/<name>.conf (GCARD_DEFAULT + run_generator()).

set -euo pipefail

# $SLURM_SUBMIT_DIR, not $BASH_SOURCE/dirname "$0" -- sbatch runs the
# script from a copied spool dir, so introspecting its own path breaks.
SCRIPT_DIR="$SLURM_SUBMIT_DIR"
WORKROOT=/project/ptgroup/Forhad/MC-HallB

NEVENTS="${NEVENTS:-1000}"
RUNNO="${RUNNO:-11}"
PHYSICS="${PHYSICS:-sidis}"
RUN_LABEL="${RUN_LABEL:-}"

TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
SEED="${SEED:-$((SLURM_JOB_ID + TASK_ID))}"
RUN_DATE=$(date +%Y%m%d)
JOBDIR="$SCRIPT_DIR/data/${PHYSICS}_${RUN_DATE}_${SLURM_JOB_ID}_${TASK_ID}"

mkdir -p "$JOBDIR/eventfiles"
cd "$JOBDIR"

cat > "$JOBDIR/run_info.txt" <<EOF
job_id: $SLURM_JOB_ID
task_id: $TASK_ID
physics: $PHYSICS
nevents_requested: $NEVENTS
seed: $SEED
submitted: $(date -Iseconds)
label: $RUN_LABEL
EOF

CONFIG_FILE="$SCRIPT_DIR/configs/${PHYSICS}.conf"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: no such physics config: $CONFIG_FILE" >&2
    ls "$SCRIPT_DIR/configs/"*.conf 2>/dev/null | xargs -n1 basename >&2
    exit 1
fi
source "$CONFIG_FILE"
GCARD="${GCARD:-$GCARD_DEFAULT}"
echo "gcard: $GCARD" >> "$JOBDIR/run_info.txt"

echo "=== RGC-ANA pipeline: job ${SLURM_JOB_ID} task ${TASK_ID} ==="
echo "PHYSICS=$PHYSICS  NEVENTS=$NEVENTS  SEED=$SEED  GCARD=$GCARD  RUNNO=$RUNNO"
echo "Working directory: $JOBDIR"
echo "Node: $(hostname)"

# --- Stage 1: generation ------------------------------------------------
echo "--- Stage 1: $PHYSICS generation ---"
run_generator "$NEVENTS" "$SEED" "$JOBDIR"

LUND_FILE="$JOBDIR/eventfiles/gen.dat"
if [[ ! -s "$LUND_FILE" ]]; then
    echo "ERROR: run_generator did not produce $LUND_FILE" >&2
    exit 1
fi

# Real kept-event count (NEVENTS may just be raw trials, e.g. genepi).
# LUND header lines have 10 fields, particle lines 14 -- count the former.
REAL_NEVENTS=$(awk 'NF==10' "$LUND_FILE" | wc -l)
if [[ "$REAL_NEVENTS" -eq 0 ]]; then
    echo "ERROR: $LUND_FILE contains 0 events" >&2
    exit 1
fi
echo "LUND file: $LUND_FILE ($REAL_NEVENTS events)"

# --- Stage 2: simulation (gemc via Apptainer sandbox) -------------------
echo "--- Stage 2: gemc simulation ---"
module purge
module load apptainer/1.4.5      # NOT 1.5.0 -- see CLAUDE.md

cp "$WORKROOT/gemc-run/$GCARD" "$JOBDIR/"

apptainer exec --bind /project:/project --pwd "$JOBDIR" \
    "$WORKROOT/gemc-sandbox-test" bash -lc \
    "gemc $GCARD -N=$REAL_NEVENTS -INPUT_GEN_FILE=\"LUND, $LUND_FILE\" -USE_GUI=0"

if [[ ! -s "$JOBDIR/out.hipo" ]]; then
    echo "ERROR: gemc did not produce out.hipo" >&2
    exit 1
fi
echo "GEMC output: $JOBDIR/out.hipo ($(du -h "$JOBDIR/out.hipo" | cut -f1))"

# --- Stage 3: reconstruction (recon-util / coatjava) --------------------
echo "--- Stage 3: recon-util reconstruction ---"
module purge
module load java/21.0.11 maven/3.9.0

COATJAVA_DIR="$WORKROOT/coatjava/coatjava"
export PATH="$COATJAVA_DIR/bin:$PATH"
export CCDB_CONNECTION="sqlite:///$WORKROOT/coatjava/coatjava/etc/data/sqlite/ccdb.sqlite"
export RCDB_CONNECTION="sqlite:///$WORKROOT/coatjava/coatjava/etc/data/sqlite/rcdb.sqlite"

recon-util -i "$JOBDIR/out.hipo" -o "$JOBDIR/out_recon.hipo" -c 1 -n "$REAL_NEVENTS"

if [[ ! -s "$JOBDIR/out_recon.hipo" ]]; then
    echo "ERROR: recon-util did not produce out_recon.hipo" >&2
    exit 1
fi
echo "Reconstructed output: $JOBDIR/out_recon.hipo ($(du -h "$JOBDIR/out_recon.hipo" | cut -f1))"

# --- Stage 4: HIPO -> ROOT (hipo2npz, then npz_to_root.py) --------------
echo "--- Stage 4: convert to ROOT ---"
hipo2npz "$JOBDIR/out_recon.hipo" "$JOBDIR/out_recon.npz" REC::Particle,REC::Event,MC::Lund

module purge
module load gcc/11.4.0 openmpi/4.1.4 python/3.11.4
source "$WORKROOT/venv/bin/activate"
python3 "$SCRIPT_DIR/npz_to_root.py" "$JOBDIR/out_recon.npz" "$JOBDIR/out_recon.root"

if [[ ! -s "$JOBDIR/out_recon.root" ]]; then
    echo "ERROR: npz_to_root.py did not produce out_recon.root" >&2
    exit 1
fi
echo "ROOT output: $JOBDIR/out_recon.root ($(du -h "$JOBDIR/out_recon.root" | cut -f1))"

echo "=== Done: job ${SLURM_JOB_ID} task ${TASK_ID} ==="
