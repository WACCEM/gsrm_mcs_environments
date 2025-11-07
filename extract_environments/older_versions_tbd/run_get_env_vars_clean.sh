#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J extract_env_vars
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
module list
conda activate /global/common/software/m1867/python/lp_env/easy

# Set up paths and parameters
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
TRACK_FILE="${ROOT_DIR}/tracking/mcs/scream/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/environmental_variables_with_LF_optimized/averaged/"

# PRECOMPUTED LAND FRACTION DATA - Key addition!
LAND_FRACTION_FILE="/pscratch/sd/p/paccini/temp/hackathon/land_fractions/mcs_land_fractions_scream_ne120_inst_summary.parquet"

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# ===== PARAMETERS TO CUSTOMIZE =====
# Model and catalog settings
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC"
CATALOG_MODEL="scream_ne120" #scream_ne120_inst
CATALOG_PARAMS='{"zoom": 8}'

# ## OPTIONAL PARAMETERS WHEN USING PRECOMPUTED VARIABLES
# PRECOMPUTED_DIR="/pscratch/sd/p/paccini/temp/hackathon/prw/${CATALOG_MODEL}_PT3H"
# PRECOMPUTED_PATTERN="scream_ne120_prw_hp8_PT3H.{year}{month:02d}.nc"

# Set spatial bounds
MIN_LAT="-30"
MAX_LAT="30"
MIN_LON="-177"
MAX_LON="177"

# Set radii for circular areas (in degrees)
RADII="5,3.5,2,0.5"

# Set track latitude/longitude variables
LAT_VAR="meanlat"
LON_VAR="meanlon"

# Processing options - Land filtering now uses precomputed data
REMOVE_LAND="--remove_land"  # Leave empty to include land areas
LAND_THRESHOLD="0.1"  # This will now filter based on precomputed land fractions
HOURS_BEFORE_INIT="24"
INCLUDE_EVOLUTION="--include_evolution"  # Leave empty to exclude evolution

# Set variables to extract 
VARIABLES=("clt") #  "clt" "tas" "ts" "huss"  "hfssd" "hflsd" "prw" sfcWind "clt""hfssd" "hflsd"   )  # Add more variables as needed "rh850" "rh500" "omega850" "omega500"

OUTPUT_FORMAT="parquet"
N_WORKERS=8  # Number of worker threads per variable

# Define date ranges for parallel processing
# DATE_RANGES=(
#   "2019-09-01 2019-12-31"  # 4 months per job
#   "2020-01-01 2020-04-30"  # 4 months per job  
#   "2020-05-01 2020-08-31"  # 4 months per job
# )
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
    echo "ERROR: Land fraction file not found: $LAND_FRACTION_FILE"
    echo "Please run run_get_land_fractions.sh first to generate the land fraction data."
    exit 1
fi

echo "Using precomputed land fraction data: $LAND_FRACTION_FILE"

# Generate all combinations of variables and date ranges
COMBINATIONS=()
for var in "${VARIABLES[@]}"; do
  for date_range in "${DATE_RANGES[@]}"; do
    COMBINATIONS+=("$var|$date_range")
  done
done

# Distribute tasks across nodes
START_IDX=0
END_IDX=$((${#COMBINATIONS[@]} - 1))

echo "Processing combinations $START_IDX to $END_IDX (out of ${#COMBINATIONS[@]} total combinations)"

MAX_CONCURRENT=16  # Maximum number of concurrent tasks (2 nodes × 128 cores ÷ 8 cores per task = 32)
RUNNING=0

# Create subfolder for each variable
create_var_subfolder() {
    local var=$1
    local dir="${OUTPUT_DIR}/${var}"
    mkdir -p "$dir"
    echo "Created subfolder for variable: $var"
    return 0
}

# Create subfolders for all variables
for var in "${VARIABLES[@]}"; do
    create_var_subfolder "$var"
done

# Process each assigned combination with srun
for ((i=START_IDX; i<=END_IDX; i++)); do
  if [ $i -lt ${#COMBINATIONS[@]} ]; then
    # Check if we've reached max concurrent jobs
    if [ $RUNNING -ge $MAX_CONCURRENT ]; then
      wait -n  # Wait for at least one job to complete
      RUNNING=$((RUNNING - 1))
    fi
    combo=${COMBINATIONS[$i]}
    var=${combo%%|*}
    date_range=${combo#*|}
    start_date=${date_range% *}
    end_date=${date_range#* }
    
    echo "Processing variable: $var for period $start_date to $end_date"
    
    srun -n 1 -c 8 --cpu_bind=cores python get_env_vars_lf_latest.py \
      --catalog_url "$CATALOG_URL" \
      --current_location "$CURRENT_LOCATION" \
      --catalog_model "$CATALOG_MODEL" \
      --catalog_params "$CATALOG_PARAMS" \
      --trackfile "$TRACK_FILE" \
      --output_dir "$OUTPUT_DIR/${var}" \
      --output_format "$OUTPUT_FORMAT" \
      --variable "$var" \
      --start_date "$start_date" \
      --end_date "$end_date" \
      --min_lat "$MIN_LAT" \
      --max_lat "$MAX_LAT" \
      --min_lon "$MIN_LON" \
      --max_lon "$MAX_LON" \
      --radii "$RADII" \
      --lat_var "$LAT_VAR" \
      --lon_var "$LON_VAR" \
      $REMOVE_LAND \
      --land_threshold "$LAND_THRESHOLD" \
      --precomputed_land_fractions "$LAND_FRACTION_FILE" \
      --hours_before_init "$HOURS_BEFORE_INIT" \
      $INCLUDE_EVOLUTION \
      --n_workers "$N_WORKERS" &
      # Note: Commented out precomputed options:
      # --precomputed_dir "$PRECOMPUTED_DIR" \
      # --precomputed_pattern "$PRECOMPUTED_PATTERN" \
      PID=$!
      RUNNING=$((RUNNING + 1))
      echo "Started job $PID for $var ($start_date - $end_date)"
  fi
done

wait
echo "All processing complete at $(date)"