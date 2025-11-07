#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J monthly_means
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# ===== PARAMETERS TO CUSTOMIZE =====

# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="online"  #  "NERSC" for SCREAM, ICON, NICAM; "online" for UM and IFS
CATALOG_MODEL="ifs_tco3999_rcbmf" # NICAM: "nicam_gl11"; SCREAM: "scream_ne120"; UM: "um_glm_n2560_RAL3p3"; ICON: "icon_d3hp003"; IFS: "ifs_tco3999_rcbmf"
CATALOG_PARAMS='{"zoom": 7}' 
# FOR 3D variables: => NICAM: '{"zoom": 6, "time":"PT6H"}'; SCREAM: '{"zoom": 6}'; UM: '{"zoom": 6, "time": "PT3H"}'; ICON: '{"zoom": 8, "time":"PT6H", "time_method":"inst"}'
# FOR 2D variables: => NICAM: '{"zoom": 6}'; SCREAM: '{"zoom": 6}'; UM: '{"zoom": 6, "time": "PT3H"}'; ICON: '{"zoom": 8, "time":"PT3H"}'
MODEL_TIME_FREQ="6H"  # Model output frequency (1H, 3H, 6H, etc.)

# Variables to process (space-separated)
# Simple 2D: tas, huss, ps
# Derived 2D: qsat (requires tas, ps, and either huss OR tdas [dew point])
#             sfcWind (computed from uas, vas if not present in dataset)
#             prw (computed from vertical integration of hus if not present - SCREAM case)
# 3D (at pressure levels): omega, hur, ta
# Derived 3D: omega (from wa - requires wa and ta)
VARIABLES="prw"  # Example: "prw tas qsat sfcWind hflsd"  "omega hur hus"
# VARIABLES="rh850 rh500 rh300"  # SCREAM only (instantaneous variables)
# Pressure levels for 3D variables (comma-separated, in hPa)
PRESSURE_LEVELS="850,500,300"  # Default levels 

# Output directory
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/large_scale_monthly_means/" #/NICAM #/SCREAM #/UM

# Date range (optional - leave empty to process all available data)
START_DATE="" #2020-03-01
END_DATE="" #2021-03-01


# ===== END PARAMETERS =====

# Create output directory
mkdir -p $OUTPUT_DIR

echo "========================================================================"
echo "Monthly Means Computation for $CATALOG_MODEL"
echo "========================================================================"
echo "Model: $CATALOG_MODEL"
echo "Location: $CURRENT_LOCATION"
echo "Variables: $VARIABLES"
echo "Pressure levels: $PRESSURE_LEVELS hPa"
echo "Output directory: $OUTPUT_DIR"
if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    echo "Date range: $START_DATE to $END_DATE"
fi
echo "========================================================================"

# Build command with optional date filtering
CMD="srun -n 1 -c 32 --cpu_bind=cores python compute_monthly_means.py \
  --catalog_url \"$CATALOG_URL\" \
  --current_location \"$CURRENT_LOCATION\" \
  --catalog_model \"$CATALOG_MODEL\" \
  --model_time_freq \"$MODEL_TIME_FREQ\" \
  --catalog_params '$CATALOG_PARAMS' \
  --variables $VARIABLES \
  --pressure_levels \"$PRESSURE_LEVELS\" \
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
