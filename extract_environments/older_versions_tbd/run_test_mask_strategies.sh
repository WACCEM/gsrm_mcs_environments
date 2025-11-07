#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J test_mask_strategies
#SBATCH -A m1867

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Test parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="${ROOT_DIR}/tracking/mcs/icon_d3hp003/stats/mcs_tracks_final_20200102.0000_20201231.2330.nc"
MASK_FILE="/pscratch/sd/w/wcmca1/hackathon/mcs/icon_d3hp003/mcstracking/icon_hrly_mcsmask_hp8_v1.zarr"

NUM_SAMPLES=5000  # Test with 5000 track-time combinations for representative results
MODEL_TIME_FREQ="3H"  # Test with 3H frequency (like ICON 2D data)

echo "Running diagnostic test for mask matching strategies"
echo "Track file: $TRACK_FILE"
echo "Mask file: $MASK_FILE"
echo "Number of samples: $NUM_SAMPLES"
echo "Model time frequency: $MODEL_TIME_FREQ"
echo "NOTE: Using STREAMING approach - no large memory loads"
echo ""

srun -n 1 -c 32 --cpu_bind=cores python test_mask_matching_strategies.py \
  --trackfile "$TRACK_FILE" \
  --mask_file "$MASK_FILE" \
  --num_samples $NUM_SAMPLES \
  --model_time_freq $MODEL_TIME_FREQ

echo ""
echo "Test complete at $(date)"
