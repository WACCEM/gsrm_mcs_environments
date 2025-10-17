#!/bin/bash
#SBATCH -A m1867
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t 03:00:00
#SBATCH -N 1
#SBATCH -J era5_env_stats
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

# ==============================================================================
# ERA5 Environmental Variable Statistics Extraction
# 
# This script processes ERA5 environmental variables that are already extracted
# in 25x25 boxes around MCS tracks and calculates statistics over circular areas.
#
# Input data structure:
# - Base directory: /global/cfs/cdirs/m1867/zfeng/gpm/mcs_global
# - Subdirectories: era5_2d (single files) and era5_2d_derived (multiple files)
# - Dimensions: tracks, rel_times, y, x
# - Spatial resolution: 0.25 degrees
#
# Author: Laura Paccini
# Date: October 2025
# ==============================================================================

module load python
module list
conda activate /global/common/software/m1867/python/lp_env/easy


# ==============================================================================
# Configuration
# ==============================================================================

# Data locations
BASE_DIR="/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global"
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/era5/"

# Time range
YEAR_START=2020
YEAR_END=2020

# Processing options
RADII="2,3"  # Radii in degrees
TIME_FREQ="3H"  # Time frequency for extraction (1H, 3H, 6H, etc.) - match model output frequency

# Track filtering (optional)
TRACK_LIST=""  # Path to file with track IDs to process (leave empty to process all)

# Variables to extract
# From era5_2d: TCWV, VAR_2T, SP, ISHF
# From era5_2d_derived: rh_850mb, rh_500mb, w_850mb, w_500mb, q_850mb, q_500mb

# Example 1: Process 2D variables
# VARIABLES=("TCWV" "VAR_2T" "SP" "ISHF")

# Example 2: Process derived variables (uncomment to use)
VARIABLES=("rh_850mb" "rh_500mb" "w_850mb" "w_500mb" "q_850mb" "q_500mb")
# VARIABLES=("rh_850mb" "rh_500mb" "w_850mb")

# Example 3: Process all variables
# VARIABLES=("TCWV" "VAR_2T" "SP" "ISHF" "rh_850mb" "rh_500mb" "w_850mb" "w_500mb" "q_850mb" "q_500mb")

# ==============================================================================
# Execution
# ==============================================================================

# Create output directory
mkdir -p "$OUTPUT_DIR"
mkdir -p logfiles

echo "Starting ERA5 statistics extraction..."
echo "Processing ${#VARIABLES[@]} variable(s) for years ${YEAR_START}-${YEAR_END}"
echo "Base directory: $BASE_DIR"
echo "Output directory: $OUTPUT_DIR"
echo "Radii: $RADII"
echo "Time frequency: $TIME_FREQ"
echo "================================================"

# Build optional parameters
OPTIONAL_PARAMS=""
if [ -n "$TRACK_LIST" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --track_list $TRACK_LIST"
fi

# Run the extraction
srun -n 1 -c 32 --cpu_bind=cores python get_stats_era5.py \
  --base_dir "$BASE_DIR" \
  --output_dir "$OUTPUT_DIR" \
  --variables "${VARIABLES[@]}" \
  --year_start "$YEAR_START" \
  --year_end "$YEAR_END" \
  --radii "$RADII" \
  --time_freq "$TIME_FREQ" \
  $OPTIONAL_PARAMS

echo "================================================"
echo "ERA5 statistics extraction completed!"
echo "Results saved to: $OUTPUT_DIR"
