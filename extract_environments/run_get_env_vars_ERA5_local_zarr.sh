#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q regular  
#SBATCH -t 01:00:00
#SBATCH -J extract_era5imergv7
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

# NOTE: For processing full year (recommended), 30 min should be sufficient
# If processing takes longer, switch to regular queue: -q regular -t 01:00:00

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/wcm_shr/hk25/mcs/"
# TRACK_FILE="${ROOT_DIR}/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc" #IMERGv7
TRACK_FILE="/pscratch/sd/f/feng045/waccem/mcs_global/stats/mcs_tracks_final_extc_20200101.0000_20210101.0000.nc" #IMERGv6
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/era5" #ERA5_IMERGv7_all"

# PRECOMPUTED LAND FRACTION DATA (from get_land_fractions.py output)
LAND_FRACTION_FILE="" #/pscratch/sd/p/paccini/temp/hackathon/updated_land_fractions/mcs_land_fractions_scream_ne120_zoom8_summary.parquet"

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# ===== OPTION 1: Direct zarr file (e.g., ERA5, observations) =====
# Uncomment to use ERA5 or other zarr files directly
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"  # Used for output naming and model-specific fixes

# ===== OPTION 2: Catalog-based models (SCREAM, ICON, IFS, etc.) =====
# Uncomment to use catalog instead of direct zarr
# ZARR_PATH=""  # Leave empty to use catalog
# CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
# CURRENT_LOCATION="NERSC"
CATALOG_MODEL="era5" #"scream_ne120_inst" for instantaneous variables
# CATALOG_PARAMS='{"zoom": 8}'

# NOTE: If ZARR_PATH is set, catalog parameters above are ignored

# Set spatial bounds
MIN_LAT="-90"
MAX_LAT="90"
MIN_LON="-180"
MAX_LON="180"

# Set radii for circular areas (in degrees)
RADII="2" #"5,3.5,2"

# Set track latitude/longitude variables
LAT_VAR="meanlat"
LON_VAR="meanlon"

# Processing options
LAND_THRESHOLD=""  # Leave empty to process all tracks, or set value like "0.1" for ocean only
HOURS_BEFORE_INIT="24"  # Extract 24 hours before track initiation
BATCH_SIZE="500"
MODEL_TIME_FREQ="3H"  # Model output frequency (1H, 3H, 6H, etc.) - SCREAM is 3-hourly
TIME_BATCH_SIZE="1000"  # Default is 1000 for other models. When loading 3D output from catalog, use time_batch_size=500 to avoid memory issues.

# Pre-computed variable options (leave empty if not using pre-computed data)
PRECOMPUTED_DIR="/pscratch/sd/p/paccini/temp/hackathon/wind_shear/ERA5/"  # Directory with pre-computed files, e.g. /pscratch/sd/p/paccini/temp/hackathon/wind_shear/ERA5/
PRECOMPUTED_PATTERN="era5_wind_shear_hp8_3H"  # Filename pattern (optional), e.g. "era5_wind_shear_hp8_3H"
TIME_RES="PT3H"  # Time resolution of pre-computed files, e.g. "PT3H"

# Set variables to extract
# VARIABLES=( "prw")  # 2D variables: Add more as needed: "tas" "hflsd" "clt" "huss"
VARIABLES=("low_shear_magnitude") # 3D slices variables: "omega500" "omega850" "rh850" "rh500" 
# VARIABLES=("hur" "omega" "hus") # 3D variables: "ta" "omega" "hus" 

# NOTE: For relative humidity (hur):
# - If 'hur' is not available in the model output, it will be automatically computed
#   from pressure, temperature (ta), and specific humidity (hus) using the
#   Clausius-Clapeyron equation
# - This is particularly useful for models like SCREAM that don't provide hur directly

# 3D variable options (for pressure level data)
PRESSURE_LEVELS=("")

# Vertical velocity conversion options
CONVERT_OMEGA_TO_WA=""  # Set to "--convert_omega_to_wa" to convert omega to wa

# ===== EXAMPLE: Convert omega to wa at 850 hPa =====
# VARIABLES=("omega")  # Start with omega variable
# PRESSURE_LEVELS="850"  # Extract at 850 hPa
# CONVERT_OMEGA_TO_WA="--convert_omega_to_wa"  # Convert omega to wa
# Output will be saved as: wa_stats_*_850hPa.parquet

# ===== EXAMPLE: Convert wa to omega at multiple levels =====
# VARIABLES=("wa")  # Start with wa variable
# PRESSURE_LEVELS="850,500,300"  # Extract at these levels
# CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"  # Convert wa to omega
# Output will be saved as: omega_stats_*_avg850-500-300hPa.parquet

# NOTE: When using pre-computed variables (PRECOMPUTED_DIR is set):
# - Default behavior: Files named like {model}_{variable}_hp{zoom}_{timeRes}.{YYYYMM}.nc
#   Example: scream_ne120_prw_hp8_PT3H.202003.nc
#   In this case, don't set PRECOMPUTED_PATTERN
#
# - For wind shear or multi-variable files: Use PRECOMPUTED_PATTERN
#   Example files: scream_ne120_wind_shear_hp8_3H.202001.nc
#   Set: PRECOMPUTED_PATTERN="scream_ne120_wind_shear_hp8_3H"
#        VARIABLES=("low_shear_magnitude" "deep_shear_magnitude")
#   The script will load the pattern file and extract the specified variables
#
# - The catalog will NOT be accessed when using pre-computed data

# ===== EXAMPLE: Extract wind shear from pre-computed files =====
# PRECOMPUTED_DIR="/pscratch/sd/p/paccini/temp/hackathon/wind_shear/SCREAM"
# PRECOMPUTED_PATTERN="scream_ne120_wind_shear_hp8_3H"
# TIME_RES="PT3H"
# VARIABLES=("low_shear_magnitude" "low_shear_direction" "deep_shear_magnitude" "deep_shear_direction")
# PRESSURE_LEVELS=""  # Not needed for pre-computed wind shear 

# Define date range for processing
# OPTION 1: Process entire year at once (RECOMMENDED - avoids duplicate tracks at month boundaries)
DATE_RANGES=(
  "2019-08-01 2020-09-02"
)

# Check if land fraction file exists
if [ ! -f "$LAND_FRACTION_FILE" ]; then
    echo "WARNING: Land fraction file not found: $LAND_FRACTION_FILE"
    echo "Will process all tracks without land fraction filtering."
    LAND_FRACTION_FILE=""
    LAND_THRESHOLD=""
fi

echo "Starting environmental variable extraction..."
echo "Processing ${#VARIABLES[@]} variable(s) across ${#DATE_RANGES[@]} date range(s)"

# Process ALL variables in a SINGLE Python call (MCS data loaded once for all)
echo "================================================"
echo "Processing all variables: ${VARIABLES[@]}"
echo "================================================"

# Build optional pre-computed parameters
OPTIONAL_PARAMS=""
if [ -n "$PRESSURE_LEVELS" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --pressure_levels $PRESSURE_LEVELS"
fi
if [ -n "$PRECOMPUTED_DIR" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --precomputed_dir $PRECOMPUTED_DIR --time_res $TIME_RES"
    echo "Using pre-computed data from: $PRECOMPUTED_DIR"
    if [ -n "$PRECOMPUTED_PATTERN" ]; then
        OPTIONAL_PARAMS="$OPTIONAL_PARAMS --precomputed_pattern $PRECOMPUTED_PATTERN"
        echo "Using filename pattern: $PRECOMPUTED_PATTERN"
    fi
fi
if [ -n "$MODEL_TIME_FREQ" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --model_time_freq $MODEL_TIME_FREQ"
fi
if [ -n "$TIME_BATCH_SIZE" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --time_batch_size $TIME_BATCH_SIZE"
fi
if [ -n "$CONVERT_WA_TO_OMEGA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_WA_TO_OMEGA"
fi
if [ -n "$CONVERT_OMEGA_TO_WA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_OMEGA_TO_WA"
fi

# Run the command with srun - pass ALL variables and date ranges to Python at once
if [ -n "$LAND_FRACTION_FILE" ] && [ -n "$LAND_THRESHOLD" ]; then
    if [ -n "$ZARR_PATH" ]; then
        # Use direct zarr file
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars.py \
          --zarr_path "$ZARR_PATH" \
          --zarr_model_name "$ZARR_MODEL_NAME" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          --land_fraction_file "$LAND_FRACTION_FILE" \
          --land_threshold "$LAND_THRESHOLD" \
          $OPTIONAL_PARAMS
    else
        # Use catalog
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars.py \
          --catalog_url "$CATALOG_URL" \
          --current_location "$CURRENT_LOCATION" \
          --catalog_model "$CATALOG_MODEL" \
          --catalog_params "$CATALOG_PARAMS" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          --land_fraction_file "$LAND_FRACTION_FILE" \
          --land_threshold "$LAND_THRESHOLD" \
          $OPTIONAL_PARAMS
    fi
elif [ -n "$LAND_FRACTION_FILE" ]; then
    if [ -n "$ZARR_PATH" ]; then
        # Use direct zarr file
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars.py \
          --zarr_path "$ZARR_PATH" \
          --zarr_model_name "$ZARR_MODEL_NAME" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          --land_fraction_file "$LAND_FRACTION_FILE" \
          $OPTIONAL_PARAMS
    else
        # Use catalog
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars.py \
          --catalog_url "$CATALOG_URL" \
          --current_location "$CURRENT_LOCATION" \
          --catalog_model "$CATALOG_MODEL" \
          --catalog_params "$CATALOG_PARAMS" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          --land_fraction_file "$LAND_FRACTION_FILE" \
          $OPTIONAL_PARAMS
    fi
else
    if [ -n "$ZARR_PATH" ]; then
        # Use direct zarr file
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars_time_batching.py \
          --zarr_path "$ZARR_PATH" \
          --zarr_model_name "$ZARR_MODEL_NAME" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          $OPTIONAL_PARAMS
    else
        # Use catalog
        srun -n 1 -c 32 --cpu_bind=cores python get_env_vars_time_batching.py \
          --catalog_url "$CATALOG_URL" \
          --current_location "$CURRENT_LOCATION" \
          --catalog_model "$CATALOG_MODEL" \
          --catalog_params "$CATALOG_PARAMS" \
          --trackfile "$TRACK_FILE" \
          --output_dir "$OUTPUT_DIR" \
          --variables "${VARIABLES[@]}" \
          --date_ranges "${DATE_RANGES[@]}" \
          --min_lat "$MIN_LAT" \
          --max_lat "$MAX_LAT" \
          --min_lon "$MIN_LON" \
          --max_lon "$MAX_LON" \
          --radii "$RADII" \
          --lat_var "$LAT_VAR" \
          --lon_var "$LON_VAR" \
          --hours_before_init "$HOURS_BEFORE_INIT" \
          --batch_size "$BATCH_SIZE" \
          $OPTIONAL_PARAMS
    fi
fi

echo "Completed processing for all variables"

echo "All processing complete at $(date)"
