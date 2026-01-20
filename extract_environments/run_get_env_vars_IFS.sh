#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t 01:30:00
#SBATCH -J extract_IFS  
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="/pscratch/sd/p/paccini/IFS_mcs_hackathon/ifs_tco3999_rcbmf/stats/mcs_tracks_final_20200101.0000_20210228.2330.nc" #IFS
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/IFS_all" #IFS_all"

# PRECOMPUTED LAND FRACTION DATA (from get_land_fractions.py output)
LAND_FRACTION_FILE=""


# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="online" # 
CATALOG_MODEL="ifs_tco3999_rcbmf" #
CATALOG_PARAMS='{"zoom": 7}'  # 

# Set spatial bounds
MIN_LAT="-90"
MAX_LAT="90"
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
MODEL_TIME_FREQ="6H"  # When loading from catalog, suggested model output frequency when using 3D output: 6H; for pre-computed data. Use 3H for 2D and pre-computed variables 
TIME_BATCH_SIZE="500"  # Default is 1000 for other models. When loading 3D output from catalog, use time_batch_size=500 to avoid memory issues.

# Pre-computed variable options (leave empty if not using pre-computed data)
PRECOMPUTED_DIR="/global/cfs/cdirs/wcm_shr/hk25/output_buoyancy/ifs_tco3999_rcbmf/"  # Directory with pre-computed files /pscratch/sd/p/paccini/temp/hackathon/wind_shear/IFS
PRECOMPUTED_PATTERN="ifs_tco3999_rcbmf_2layers_BLcomponents_hp7_6H"  # Filename pattern (optional), e.g. "ifs_tco3999_rcbmf_wind_shear_hp7_3H"
TIME_RES="PT6H"  # Time resolution of pre-computed files, e.g. "PT3H"

# 3D variable options (for pressure level data)
PRESSURE_LEVELS=("") # For 3D variables, specify levels: "850,500,300" 850,800,750,700,600,500
CONVERT_OMEGA_TO_WA=""  # Set to "--convert_omega_to_wa" to convert omega to wa

# Set variables to extract
# VARIABLES=("hur")  # Add more as needed: "tas" "hflsd" "clt" "huss" "tcwv"
# VARIABLES=("low_shear_magnitude_975hPa-800hPa" "deep_shear_magnitude_850hPa-400hPa") # "omega" "hur"
VARIABLES=("BL_TOT" "BL_CAPE" "BL_SUBSAT" ) #"thetae_bl" "thetae_lt_sat"
# ===== EXAMPLE: Extract wa at 850 hPa from IFS =====
# Uncomment these lines to extract wa at 850 hPa:
# CATALOG_MODEL="ifs_tco3999_rcbmf"
# CATALOG_PARAMS='{"zoom": 7}'  # Required for 3D data      
# VARIABLES=("omega")  # Process vertical velocity
# PRESSURE_LEVELS="850"  # Extract at 850 hPa
# CONVERT_OMEGA_TO_WA="--convert_omega_to_wa"  # Convert omega to wa
# Output will be saved as: *.parquet

# Define monthly date ranges for processing
DATE_RANGES=( 
  "2020-01-01 2021-03-01"
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
# Build optional 3D parameters
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
if [ -n "$CONVERT_OMEGA_TO_WA" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS $CONVERT_OMEGA_TO_WA"
fi
if [ -n "$MODEL_TIME_FREQ" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --model_time_freq $MODEL_TIME_FREQ"
fi
if [ -n "$TIME_BATCH_SIZE" ]; then
    OPTIONAL_PARAMS="$OPTIONAL_PARAMS --time_batch_size $TIME_BATCH_SIZE"
fi

if [ -n "$LAND_FRACTION_FILE" ] && [ -n "$LAND_THRESHOLD" ]; then
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
      --land_fraction_file "$LAND_FRACTION_FILE" \
      --land_threshold "$LAND_THRESHOLD" \
      $OPTIONAL_PARAMS
elif [ -n "$LAND_FRACTION_FILE" ]; then
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
      --land_fraction_file "$LAND_FRACTION_FILE" \
      $OPTIONAL_PARAMS
else
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

echo "Completed processing for all variables"

echo "All processing complete at $(date)"
