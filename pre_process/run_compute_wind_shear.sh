#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J wind_shear
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# ===== PARAMETERS TO CUSTOMIZE =====

# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC"  #  "NERSC" for SCREAM, ICON, NICAM; "online" for UM and IFS
CATALOG_MODEL="icon_d3hp003" # NICAM: "nicam_gl11"; SCREAM: "scream_ne120"; UM: "um_glm_n2560_RAL3p3"; ICON: "icon_d3hp003"
CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}' # NICAM: '{"zoom": 8, "time":"PT6H"}'; SCREAM: '{"zoom": 8}'; UM: '{"zoom": 8, "time": "PT3H"}'; ICON: '{"zoom": 8, "time":"PT6H", "time_method":"inst"}'
MODEL_TIME_FREQ="6H"  # Model output frequency (1H, 3H, 6H, etc.)


# Output directory
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/wind_shear/ICON" #/NICAM #/SCREAM #/UM

# Date range (optional - leave empty to process all available data)
START_DATE="" #2020-03-01
END_DATE="" #2021-03-01

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
  --output_dir \"$OUTPUT_DIR\""

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
