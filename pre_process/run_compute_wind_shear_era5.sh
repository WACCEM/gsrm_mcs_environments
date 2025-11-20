#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t 01:30:00
#SBATCH -J wind_shear_era5
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# ===== PARAMETERS TO CUSTOMIZE =====

# ===== OPTION 1: Direct zarr file (e.g., ERA5, observations) =====
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"  # Used for output naming and model-specific fixes

# ===== OPTION 2: Catalog-based models (SCREAM, ICON, IFS, etc.) =====
# Uncomment to use catalog instead of direct zarr
# ZARR_PATH=""  # Leave empty to use catalog
# CATALOG_URL="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
# CURRENT_LOCATION="online"
CATALOG_MODEL="era5"
# CATALOG_PARAMS='{"zoom": 7}'
MODEL_TIME_FREQ="3H"  # Model output frequency

# Output directory
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/wind_shear/ERA5"

# Date range (optional - leave empty to process all available data)
START_DATE="2019-08-01"
END_DATE="2021-03-01" #"2021-03-01"  "


# ===== END PARAMETERS =====

# Create output directory
mkdir -p $OUTPUT_DIR

echo "========================================================================"
echo "Wind Shear Computation"
echo "========================================================================"
if [ -n "$ZARR_PATH" ]; then
    echo "Model: $ZARR_MODEL_NAME (zarr)"
    echo "Zarr path: $ZARR_PATH"
else
    echo "Model: $CATALOG_MODEL"
    echo "Location: $CURRENT_LOCATION"
fi
echo "Output directory: $OUTPUT_DIR"
if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    echo "Date range: $START_DATE to $END_DATE"
fi
echo "========================================================================"

# Build command based on zarr vs catalog
if [ -n "$ZARR_PATH" ]; then
    # Use direct zarr file
    CMD="srun -n 1 -c 32 --cpu_bind=cores python compute_wind_shear.py \
      --zarr_path \"$ZARR_PATH\" \
      --zarr_model_name \"$ZARR_MODEL_NAME\" \
      --model_time_freq \"$MODEL_TIME_FREQ\" \
      --output_dir \"$OUTPUT_DIR\""
else
    # Use catalog
    CMD="srun -n 1 -c 32 --cpu_bind=cores python compute_wind_shear.py \
      --catalog_url \"$CATALOG_URL\" \
      --current_location \"$CURRENT_LOCATION\" \
      --catalog_model \"$CATALOG_MODEL\" \
      --model_time_freq \"$MODEL_TIME_FREQ\" \
      --catalog_params '$CATALOG_PARAMS' \
      --output_dir \"$OUTPUT_DIR\""
fi

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
