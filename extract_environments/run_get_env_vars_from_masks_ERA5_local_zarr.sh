#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t 02:30:00
#SBATCH -J extract_era5_masks
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/wcm_shr/hk25/mcs/"
TRACK_FILE="${ROOT_DIR}/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc" #IMERGv7
# TRACK_FILE="/pscratch/sd/f/feng045/waccem/mcs_global/stats/mcs_tracks_final_extc_20200101.0000_20210101.0000.nc" #IMERGv6
MASK_FILE="/pscratch/sd/w/wcmca1/hackathon/mcs/IMERGv7/mcstracking/IMERGv7_hrly_mcsmask_hp8_v1.zarr" #IMERGv7
# MASK_FILE="/pscratch/sd/w/wcmca1/hackathon/mcs/IMERGv6/mcstracking/IMERGv6_hrly_mcsmask_hp8_v1.zarr" #IMERGv6
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/ERA5_IMERGv7_all/from_masks" #IMERGv7
# OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/era5/from_masks" #IMERGv6

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Direct zarr file path (ERA5)
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"  # Used for output naming and model-specific fixes

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
VARIABLES=("hflsd" "tas" "hfssd" "sfcWind" "ps")  # Add more as needed: "prw" "tas" "huss" "clt" "hfssd" "ps" "sfcWind"

# NOTE: For ERA5, when extracting "hflsd" (surface latent heat flux):
# - The script will automatically use "ie" (instantaneous moisture flux) if "hflsd" is not available
# - Conversion formula: hflsd = -ie × 2.26e6 (accounts for ECMWF positive-downward convention)
# ===== EXAMPLE: Extract omega at 850 hPa from ERA5 =====
# Uncomment these lines to extract omega at 850 hPa:
# VARIABLES=("omega")
# PRESSURE_LEVELS="850"
# CONVERT_OMEGA_TO_WA=""  # Keep empty for omega, or add "--convert_omega_to_wa" to convert to wa

# ===== EXAMPLE: Extract multiple 3D variables at multiple levels =====
# VARIABLES=("omega" "hus" "ta")
# PRESSURE_LEVELS="850,500,300"  # Extract at these three levels (averaged)

# ===== EXAMPLE: Extract surface wind speed =====
# VARIABLES=("sfcWind")  # Will be computed from uas and vas

# Define date range for processing
# Each start and end date should be SEPARATE array elements
# For IMERGv7 tracks
DATE_RANGES=(
  "2019-08-01"
  "2020-09-02"
)
# ## For IMERGv6 tracks
# DATE_RANGES=(
#   "2020-01-01"
#   "2021-01-01"
# )

echo "Starting mask-based environmental variable extraction from ERA5..."
echo "Processing ${#VARIABLES[@]} variable(s) across $((${#DATE_RANGES[@]} / 2)) date range(s)"
echo "Zarr file: $ZARR_PATH"
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
  --zarr_path "$ZARR_PATH" \
  --zarr_model_name "$ZARR_MODEL_NAME" \
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
