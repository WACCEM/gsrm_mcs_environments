#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J extract_icon
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
module list
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="${ROOT_DIR}/tracking/mcs/icon_d3hp003/stats/mcs_tracks_final_20200102.0000_20201231.2330.nc" #ICON
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/ICON"

# PRECOMPUTED LAND FRACTION DATA (from get_land_fractions.py output)
LAND_FRACTION_FILE="/pscratch/sd/p/paccini/temp/hackathon/updated_land_fractions/mcs_land_fractions_icon_d3hp003_zoom8_summary.parquet" # for ICON


# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC" 
CATALOG_MODEL="icon_d3hp003" 
CATALOG_PARAMS='{"zoom": 8 }'  # For 3D ICON data, use: '{"zoom": 8, time="PT6H",time_method='inst'}'

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
MODEL_TIME_FREQ="3H"  # Model output frequency (1H, 3H, 6H, etc.) - ICON is 6-hourly for 3D

# 3D variable options (for pressure level data)
PRESSURE_LEVELS=("")  # For 3D variables, specify levels: "850,500,300"
CONVERT_WA_TO_OMEGA=""  # Set to "--convert_wa_to_omega" to convert wa to omega

# Set variables to extract
VARIABLES=( "huss" "ps")  # Add more as needed: "tas" "hflsd" "clt"  "prw"
# VARIABLES=("wa") #"wa, hur
# ===== EXAMPLE: Extract omega at 850 hPa from ICON =====
# Uncomment these lines to extract omega at 850 hPa:
# CATALOG_MODEL="icon_d3hp003"
# CATALOG_PARAMS='{"zoom": 8, time="PT6H",time_method='inst'}'  # Required for 3D data
# VARIABLES=("wa")  # Process vertical velocity
# PRESSURE_LEVELS="850"  # Extract at 850 hPa
# CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"  # Convert wa to omega
# Output will be saved as: omega_stats_*.parquet

# ===== EXAMPLE: Extract multiple 3D variables at multiple levels =====
# CATALOG_MODEL="icon_d3hp003"
# CATALOG_PARAMS='{"zoom": 8, time="PT6H",time_method='inst'}'
# VARIABLES=("wa" "hus" "ta")
# PRESSURE_LEVELS="850,500,300"  # Extract at these three levels
# CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"  # Only affects 'wa'

# Define monthly date ranges for processing
DATE_RANGES=(
  "2020-01-01 2020-01-31"
  "2020-02-01 2020-02-29"
  "2020-03-01 2020-03-31"
  "2020-04-01 2020-04-30"
  "2020-05-01 2020-05-31"
  "2020-06-01 2020-06-30"
  "2020-07-01 2020-07-31"
  "2020-08-01 2020-08-31"
  "2020-09-01 2020-09-30"
  "2020-10-01 2020-10-31"
  "2020-11-01 2020-11-30"
  "2020-12-01 2020-12-31"
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

# Run the command with srun - pass ALL variables and date ranges to Python at once
# Build optional parameters
OPTIONAL_PARAMS=""
if [ -n "$PRESSURE_LEVELS" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --pressure_levels $PRESSURE_LEVELS"
fi
if [ -n "$CONVERT_WA_TO_OMEGA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_WA_TO_OMEGA"
fi
if [ -n "$MODEL_TIME_FREQ" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --model_time_freq $MODEL_TIME_FREQ"
fi

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
