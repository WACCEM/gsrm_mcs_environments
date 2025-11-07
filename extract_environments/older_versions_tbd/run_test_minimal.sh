#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:10:00
#SBATCH -J test_minimal
#SBATCH -A m1867

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Test parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="${ROOT_DIR}/tracking/mcs/icon_d3hp003/stats/mcs_tracks_final_20200102.0000_20201231.2330.nc"
MASK_FILE="/pscratch/sd/w/wcmca1/hackathon/mcs/icon_d3hp003/mcstracking/icon_hrly_mcsmask_hp8_v1.zarr"

echo "Running MINIMAL mask access test"
echo "This tests basic zarr access patterns"
echo ""

srun -n 1 -c 4 --cpu_bind=cores python test_mask_minimal.py \
  --mask_file "$MASK_FILE" \
  --track_file "$TRACK_FILE"

echo ""
echo "Test complete at $(date)"
