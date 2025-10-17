#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J extract_scream
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
module list
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="${ROOT_DIR}/tracking/mcs/scream/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/SCREAM"

# PRECOMPUTED LAND FRACTION DATA (from get_land_fractions.py output)
LAND_FRACTION_FILE="/pscratch/sd/p/paccini/temp/hackathon/updated_land_fractions/mcs_land_fractions_scream_ne120_zoom8_summary.parquet"

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC"
CATALOG_MODEL="scream_ne120_inst" #"scream_ne120_inst" for instantaneous variables
CATALOG_PARAMS='{"zoom": 8}'

# Set spatial bounds
MIN_LAT="-30"
MAX_LAT="30"
MIN_LON="-180"
MAX_LON="180"

# Set radii for circular areas (in degrees)
RADII="5,3.5,2"

# Set track latitude/longitude variables
LAT_VAR="meanlat"
LON_VAR="meanlon"

# Processing options
LAND_THRESHOLD=""  # Leave empty to process all tracks, or set value like "0.1" for ocean only
HOURS_BEFORE_INIT="24"  # Extract 24 hours before track initiation
BATCH_SIZE="500"
MODEL_TIME_FREQ="3H"  # Model output frequency (1H, 3H, 6H, etc.) - SCREAM is 3-hourly

# Pre-computed variable options (leave empty if not using pre-computed data)
PRECOMPUTED_DIR=""  # Directory with pre-computed files, e.g. /pscratch/sd/p/paccini/temp/hackathon/prw/${CATALOG_MODEL}_PT3H
TIME_RES=""  # Time resolution of pre-computed files, e.g. "PT3H"

# Set variables to extract
# VARIABLES=( "tas")  # Add more as needed: "tas" "hflsd" "clt" "huss"
VARIABLES=("rh500") #"omega500" "omega850" "rh850" "rh500" 

# NOTE: When using pre-computed variables (PRECOMPUTED_DIR is set):
# - The script will load data from files like: scream_ne120_prw_hp8_PT3H.202003.nc
# - Expected filename pattern: {model}_{variable}_hp{zoom}_{timeRes}.{YYYYMM}.nc
# - The catalog will NOT be accessed for this variable 
# Define monthly date ranges for processing
DATE_RANGES=(
  "2019-08-01 2019-08-31"
  "2019-09-01 2019-09-30"
  "2019-10-01 2019-10-31"
  "2019-11-01 2019-11-30"
  "2019-12-01 2019-12-31"
  "2020-01-01 2020-01-31"
  "2020-02-01 2020-02-29"
  "2020-03-01 2020-03-31"
  "2020-04-01 2020-04-30"
  "2020-05-01 2020-05-31"
  "2020-06-01 2020-06-30"
  "2020-07-01 2020-07-31"
  "2020-08-01 2020-08-31"
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
if [ -n "$PRECOMPUTED_DIR" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --precomputed_dir $PRECOMPUTED_DIR --time_res $TIME_RES"
    echo "Using pre-computed data from: $PRECOMPUTED_DIR"
fi
if [ -n "$MODEL_TIME_FREQ" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --model_time_freq $MODEL_TIME_FREQ"
fi

# Run the command with srun - pass ALL variables and date ranges to Python at once
if [ -n "$LAND_FRACTION_FILE" ] && [ -n "$LAND_THRESHOLD" ]; then
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
elif [ -n "$LAND_FRACTION_FILE" ]; then
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
else
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
      $OPTIONAL_PARAMS
fi

echo "Completed processing for all variables"

echo "All processing complete at $(date)"
