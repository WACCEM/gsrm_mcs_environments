#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J extract_scream_masks
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/pscratch/sd/w/wcmca1/hackathon/mcs/scream/"
TRACK_FILE="${ROOT_DIR}/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
MASK_FILE="${ROOT_DIR}/mcstracking/scream2D_hrly_mcsmask_hp8_v1.zarr"
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/SCREAM_all/from_masks"

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC" 
CATALOG_MODEL="scream_ne120" 
CATALOG_PARAMS='{"zoom": 8}'  # For 3D  data, use: '{"zoom": 8, "time": "PT6H", "time_method": "inst"}'

# Set spatial bounds
MIN_LAT="-90"
MAX_LAT="90"
MIN_LON="-180"
MAX_LON="180"

# Set track latitude/longitude variables
LAT_VAR="meanlat"
LON_VAR="meanlon"

# Processing options
BATCH_SIZE="50"  # Number of unique times to load at once (optimized for memory efficiency)
MODEL_TIME_FREQ="3H"  # Model output frequency (1H, 3H, 6H, etc.)

# 3D variable options (for pressure level data)
PRESSURE_LEVELS=""  # For 3D variables, specify levels: "850,500,300"
CONVERT_WA_TO_OMEGA=""  # Set to "--convert_wa_to_omega" to convert wa to omega
CONVERT_OMEGA_TO_WA=""  # Set to "--convert_omega_to_wa" to convert omega to wa

# Set variables to extract
VARIABLES=("sfcWind" "huss" )  # Add more as needed: "prw" "hflsd" "clt" "sfcWind" hflsd


# ===== EXAMPLE: Extract surface wind speed =====
# VARIABLES=("sfcWind")  # Will be computed from uas and vas
# Note: Make sure uas and vas are available in the 2D catalog

# Define date range for processing
# Each start and end date should be SEPARATE array elements
DATE_RANGES=(
  "2019-08-01"
  "2020-09-02"
)
# ====================================================================

echo "Starting mask-based environmental variable extraction..."
echo "Processing ${#VARIABLES[@]} variable(s) across $((${#DATE_RANGES[@]} / 2)) date range(s)"
echo "Mask file: $MASK_FILE"

# Build optional parameters
OPTIONAL_PARAMS=""
if [ -n "$PRESSURE_LEVELS" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --pressure_levels $PRESSURE_LEVELS"
    echo "Using pressure levels: $PRESSURE_LEVELS hPa"
fi
if [ -n "$CONVERT_WA_TO_OMEGA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_WA_TO_OMEGA"
    echo "Will convert wa to omega"
fi
if [ -n "$CONVERT_OMEGA_TO_WA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_OMEGA_TO_WA"
    echo "Will convert omega to wa"
fi
if [ -n "$MODEL_TIME_FREQ" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --model_time_freq $MODEL_TIME_FREQ"
    echo "Model time frequency: $MODEL_TIME_FREQ"
fi

# Run the extraction
echo "================================================"
echo "Processing all variables: ${VARIABLES[@]}"
echo "================================================"

srun -n 1 -c 32 --cpu_bind=cores python get_env_vars_from_masks.py \
  --catalog_url "$CATALOG_URL" \
  --current_location "$CURRENT_LOCATION" \
  --catalog_model "$CATALOG_MODEL" \
  --catalog_params "$CATALOG_PARAMS" \
  --trackfile "$TRACK_FILE" \
  --mask_file "$MASK_FILE" \
  --output_dir "$OUTPUT_DIR" \
  --variables "${VARIABLES[@]}" \
  --date_ranges "${DATE_RANGES[@]}" \
  --min_lat "$MIN_LAT" \
  --max_lat "$MAX_LAT" \
  --min_lon "$MIN_LON" \
  --max_lon "$MAX_LON" \
  --lat_var "$LAT_VAR" \
  --lon_var "$LON_VAR" \
  --batch_size "$BATCH_SIZE" \
  $OPTIONAL_PARAMS

echo "Completed processing for all variables"
echo "All processing complete at $(date)"
