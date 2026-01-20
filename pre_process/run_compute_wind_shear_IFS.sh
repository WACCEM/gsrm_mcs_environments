#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t 06:00:00
#SBATCH -J wind_shear_ifs
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# ===== PARAMETERS TO CUSTOMIZE =====

# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="online"  # 
CATALOG_MODEL="ifs_tco3999_rcbmf"
CATALOG_PARAMS='{"zoom": 7}'
MODEL_TIME_FREQ="3H"  # Model output frequency (Suggested 6H for IFS)


# Output directory
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/new_wind_shear/IFS"

# Date range (optional - leave empty to process all available data)
START_DATE=""
END_DATE="" #"2021-03-01"
# Pressure levels for wind shear computation (in hPa)
# Format: "lower,upper" where shear = upper - lower
# Multiple ranges can be specified separated by semicolons
# Examples:
#   Single range: "975,800"
#   Multiple ranges: "1000,800;975,800"
LOW_SHEAR_LEVELS="1000,800; 975,800; 950,800"    # Default: 975-800 hPa (low-level shear)
DEEP_SHEAR_LEVELS="850,400; 800,400"   # Default: 850-400 hPa (deep-layer shear)

# ===== END PARAMETERS =====

# Create output directory
mkdir -p $OUTPUT_DIR

echo "========================================================================"
echo "Wind Shear Computation for $CATALOG_MODEL"
echo "========================================================================"
echo "Model: $CATALOG_MODEL"
echo "Location: $CURRENT_LOCATION"
echo "Output directory: $OUTPUT_DIR"
if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    echo "Date range: $START_DATE to $END_DATE"
fi
echo "========================================================================"

# Build command with optional date filtering
CMD="srun -n 1 -c 32 --cpu_bind=cores python compute_wind_shear.py \
  --catalog_url \"$CATALOG_URL\" \
  --current_location \"$CURRENT_LOCATION\" \
  --catalog_model \"$CATALOG_MODEL\" \
  --model_time_freq \"$MODEL_TIME_FREQ\" \
  --catalog_params '$CATALOG_PARAMS' \
  --output_dir \"$OUTPUT_DIR\"\
  --low_shear_levels \"$LOW_SHEAR_LEVELS\" \
  --deep_shear_levels \"$DEEP_SHEAR_LEVELS\""
# Add date range if specified
if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    CMD="$CMD --start_date \"$START_DATE\" --end_date \"$END_DATE\""
fi

# Execute command
echo "Executing: $CMD"
eval $CMD

echo ""
echo "========================================================================"
echo "Processing complete at $(date)"
echo "========================================================================"
