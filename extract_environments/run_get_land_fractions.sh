#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -J extract_land
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# ===== PATHS AND FILES =====
ROOT_DIR="/global/cfs/cdirs/m4581/gsharing/hackathon"
# TRACK_FILE="${ROOT_DIR}/tracking/mcs/scream/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc" #SCREAM
# TRACK_FILE="/pscratch/sd/w/wcmca1/hackathon/mcs/nicam_gl11/stats/mcs_tracks_final_20200301.0000_20210301.0000.nc" #NICAM
# TRACK_FILE="/pscratch/sd/f/feng045/waccem/mcs_global/stats/mcs_tracks_final_extc_20200101.0000_20210101.0000.nc" #OBS
TRACK_FILE="/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc" #IMERGv7
# TRACK_FILE="/pscratch/sd/p/paccini/IFS_mcs_hackathon/ifs_tco3999_rcbmf/stats/mcs_tracks_final_20200101.0000_20210228.2330.nc" #IFS
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_land_fractions/for_era5_imergv7/"
mkdir -p $OUTPUT_DIR

# ===== MODEL AND CATALOG SETTINGS =====
CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CURRENT_LOCATION="NERSC"
CATALOG_MODEL="scream_ne120" #""
CATALOG_PARAMS='{"zoom": 8}'
LAND_FRACTION_VAR="LANDFRAC"

# ===== PROCESSING OPTIONS =====
RADII="5,3.5,2"
LAT_VAR="meanlat"
LON_VAR="meanlon"
START_DATE="2020-01-01"
END_DATE="2021-03-01"
OUTPUT_FORMAT="parquet"

# ===== SPATIAL BOUNDS =====
MIN_LAT="-90"
MAX_LAT="90"
MIN_LON="-180"
MAX_LON="180"

# ===== RUN SCRIPT V2 (optimized with batched approach - 1.5x faster!) =====
echo "=========================================="
echo "Land Fraction Extraction v2 (Batched)"
echo "=========================================="
echo "Model: $CATALOG_MODEL"
echo "Catalog params: $CATALOG_PARAMS"
echo "Date range: $START_DATE to $END_DATE"
echo "Output directory: $OUTPUT_DIR"
echo "=========================================="

srun -n 1 -c 32 --cpu_bind=cores python get_land_fractions.py \
  --catalog_url "$CATALOG_URL" \
  --current_location "$CURRENT_LOCATION" \
  --catalog_model "$CATALOG_MODEL" \
  --catalog_params "$CATALOG_PARAMS" \
  --trackfile "$TRACK_FILE" \
  --output_dir "$OUTPUT_DIR" \
  --output_format "$OUTPUT_FORMAT" \
  --land_fraction_var "$LAND_FRACTION_VAR" \
  --start_date "$START_DATE" \
  --end_date "$END_DATE" \
  --min_lat "$MIN_LAT" \
  --max_lat "$MAX_LAT" \
  --min_lon "$MIN_LON" \
  --max_lon "$MAX_LON" \
  --radii "$RADII" \
  --lat_var "$LAT_VAR" \
  --lon_var "$LON_VAR"

echo ""
echo "=========================================="
echo "Extraction completed at $(date)"
echo "=========================================="
