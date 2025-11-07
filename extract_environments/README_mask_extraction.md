# Mask-Based Environmental Variable Extraction# Mask-Based Environmental Variable Extraction



Extract environmental statistics using actual MCS spatial masks instead of circular areas. This provides a more accurate representation of the MCS spatial extent by using the exact cloud boundaries.This directory contains scripts for extracting environmental variables around MCS tracks using two approaches:



**Script:** `get_env_vars_from_masks.py`  1. **Circular Area Extraction** (`get_env_vars_backup_last.py`)

**Author:** Laura Paccini     - Extracts statistics within circular areas around track centroids

**Last Updated:** November 2025   - Supports multiple radii (e.g., 5°, 3.5°, 2°)

   - Includes pre-convective period (24h before track initiation)

---   - Uses HEALPix grid calculations



## Overview2. **Mask-Based Extraction** (`get_env_vars_from_masks.py`) ⭐ **NEW**

   - Extracts statistics using actual MCS mask boundaries

Mask-based extraction uses MCS tracking masks (zarr format) where each mask contains track IDs indicating which grid cells belong to each MCS at each time step. This approach extracts environmental statistics for all cells within the actual MCS boundaries.   - No radius parameter (mask defines the area)

   - Track duration only (no pre-convective period)

### Key Features   - More accurate representation of actual MCS extent



- ✅ Uses actual MCS boundaries (no approximation)## Files Created

- ✅ Extracts statistics for exact MCS extent

- ✅ Handles hourly masks with 3H/6H model output### Core Scripts

- ✅ Supports 2D and 3D variables- `env_extraction_utils.py` - Common utility functions shared between both approaches

- ✅ Memory-efficient small-batch processing  - Time conversion and alignment

- ❌ No pre-convective period (track duration only)  - Pressure level handling and unit detection

- ❌ No radius parameter (mask defines area)  - Vertical velocity conversions (wa ↔ omega)

  - Model-specific dimension/variable name fixes

---  - Surface wind speed computation



## Quick Start- `get_env_vars_from_masks.py` - Main script for mask-based extraction

  - Loads MCS mask file (zarr format)

```bash  - Matches track IDs with mask values

# Run with bash script  - Extracts statistics for all cells within each mask

sbatch run_get_env_vars_from_masks_SCREAM.sh  - Handles hourly masks vs 3H/6H model output



# Or run Python directly- `run_get_env_vars_from_masks_ICON.sh` - Example bash script for ICON model

python get_env_vars_from_masks.py \

  --catalog_model "scream_ne120" \## Key Differences: Circular vs Mask-Based

  --catalog_params '{"zoom": 8, "time": "PT3H"}' \

  --trackfile "/path/to/tracks.nc" \| Feature | Circular Areas | Mask-Based |

  --mask_file "/path/to/masks.zarr" \|---------|---------------|------------|

  --variables tas huss \| Spatial extent | Fixed radius circles | Actual MCS boundaries |

  --model_time_freq "3H" \| Pre-convective | ✅ 24h before init | ❌ Track duration only |

  --output_dir "/path/to/output"| Radius parameter | Multiple radii | None (from mask) |

```| Accuracy | Approximate area | Exact MCS extent |

| Output columns | Includes `radius` | No `radius` column |

---| Use case | Quick analysis, environment | Detailed MCS analysis |



## Key Differences: Circular vs Mask-BasedBoth approaches include `time_offset_hours` to track position within lifecycle.



| Feature | Circular Areas | Mask-Based |## Usage Example

|---------|---------------|------------|

| Spatial extent | Fixed radius circles | Actual MCS boundaries |### Basic 2D Variables

| Pre-convective | ✅ 24h before init | ❌ Track duration only |```bash

| Radius parameter | Multiple radii | None (from mask) |# Extract surface temperature, humidity, and heat flux

| Accuracy | Approximate area | Exact MCS extent |VARIABLES=("tas" "huss" "hfssd")

| Output columns | Includes `radius` | No `radius` column |MODEL_TIME_FREQ="3H"

| Use case | Environment around MCS | MCS internal structure |```

| Script | `get_env_vars.py` | `get_env_vars_from_masks.py` |

### Surface Wind Speed

Both approaches include `time_offset_hours` to track position within lifecycle.```bash

# Automatically computed from uas and vas

---VARIABLES=("sfcWind")

```

## Input Requirements

### 3D Variables with Pressure Levels

### 1. MCS Track File (NetCDF)```bash

Standard track statistics file with:# Extract specific humidity at 850 hPa

- `tracks` - Track IDsVARIABLES=("hus")

- `times` - Time indices  PRESSURE_LEVELS="850"

- `base_time` - TimestampsMODEL_TIME_FREQ="6H"  # 3D data usually 6-hourly

- `meanlat`, `meanlon` - Track positions (for filtering)CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}'

```

### 2. MCS Mask File (Zarr)

Zarr dataset with mask variable containing track IDs:### Vertical Velocity Conversion

- **Dimensions:** `(time, cell)` for HEALPix grid```bash

- **Variable:** `mcs_mask` - Integer track IDs (0 = no MCS, >0 = track ID)# Convert wa to omega at multiple levels

- **Time resolution:** Typically hourlyVARIABLES=("wa")

PRESSURE_LEVELS="850,500,300"  # Will be averaged

**Example mask structure:**CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"

```# Output saved as: omega_stats_*_avg850-500-300hPa.parquet

mcs_mask.zarr/```

├── time/          # Hourly timestamps

├── cell/          # HEALPix cell indices## Time Alignment

└── mcs_mask/      # Track IDs at each (time, cell)

```The script handles different temporal resolutions:



### 3. Model Data (via Catalog)1. **Track files**: Hourly output

Environmental variables from intake catalog:2. **Mask files**: Hourly output (matches tracks)

- 2D variables: `tas`, `huss`, `prw`, etc.3. **Model data**: Can be 1H, 3H, 6H, etc.

- 3D variables: `ta`, `hus`, `hur`, `wa`, etc. (with pressure levels)

**Strategy:**

---- Subsample tracks to match `MODEL_TIME_FREQ` (e.g., keep 00:00, 03:00, 06:00 for 3H)

- Use nearest-neighbor matching between subsampled times and model times

## Usage Examples- Extract mask at the (hourly) track time, then find nearest model time for variable



### Example 1: Basic 2D Variables## Output Format

```bash

# Extract surface temperature, humidity, and heat fluxResults saved as parquet files with columns:

VARIABLES=("tas" "huss" "hfss")- `track_id` - Track identifier

MODEL_TIME_FREQ="3H"- `time_idx` - Time index within track

CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'- `data_time` - Actual timestamp

```- `time_offset_hours` - Hours since track initiation

- `mean`, `median`, `min`, `max`, `std` - Statistics

### Example 2: Surface Wind Speed- `count` - Total number of cells in mask

```bash- `num_valid` - Number of non-NaN cells

# Automatically computed from uas and vas

VARIABLES=("sfcWind")## Model-Specific Considerations

MODEL_TIME_FREQ="3H"

```### ICON

```bash

### Example 3: 3D Variables with Pressure LevelsCATALOG_MODEL="icon_d3hp003"

```bashCATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'  # 2D data

# Extract specific humidity at 850 hPa# For 3D: '{"zoom": 8, "time": "PT6H", "time_method": "inst"}'

VARIABLES=("hus")MODEL_TIME_FREQ="3H"  # or "6H" for 3D

PRESSURE_LEVELS="850"```

MODEL_TIME_FREQ="6H"

CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}'### SCREAM

``````bash

CATALOG_MODEL="scream_ne120"

### Example 4: Vertical Velocity ConversionCATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'

```bashMODEL_TIME_FREQ="3H"

# Convert wa to omega at multiple levels (averaged)```

VARIABLES=("wa")

PRESSURE_LEVELS="850,500,300"### IFS

CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"```bash

CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}'CATALOG_MODEL="ifs"

CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'

# Output: omega_stats_omega_avg850-500-300hPa.parquetMODEL_TIME_FREQ="3H"

```# Note: IFS uses different dimension/variable names (auto-fixed)

```

### Example 5: Multiple Variables at Once

```bash## Performance Tips

VARIABLES=("tas" "huss" "prw" "sfcWind")

MODEL_TIME_FREQ="3H"1. **Batch size**: Default 500 is good balance. Increase for more memory, decrease if OOM.

2. **Date ranges**: Split into monthly chunks for large datasets

# All variables processed in one run (efficient!)3. **Variables**: Process multiple variables in one run (dataset loaded once)

```4. **Spatial filtering**: Restrict lat/lon bounds to region of interest



---## Common Issues



## Time Alignment Strategy### Time Mismatch

If tracks don't align with model times:

The script handles different temporal resolutions intelligently:- Check `MODEL_TIME_FREQ` matches actual model output

- Verify catalog `time` parameter (PT3H vs PT6H)

### Time Frequencies- Use `time_method="inst"` for instantaneous 3D data

1. **Track files:** Hourly output (1H)

2. **Mask files:** Hourly output (1H) - matches tracks### Missing Variables

3. **Model data:** Variable (1H, 3H, 6H, etc.)- Check variable name in catalog (may differ by model)

- For sfcWind: ensure uas/vas are in 2D catalog

### Alignment Process- For 3D: verify pressure dimension exists



**Step 1: Subsample tracks to model frequency**### Empty Results

```- Verify mask file path and format

Track times (hourly):  00:00, 01:00, 02:00, 03:00, 04:00, 05:00, 06:00, ...- Check track IDs exist in mask (mcs_mask values match track_id)

Model freq (3H):      00:00,       03:00,       06:00, ...- Confirm spatial/temporal overlap between tracks and model data

Subsampled:           00:00,       03:00,       06:00, ...

```## Future Enhancements



**Step 2: Match subsampled times with model output**Potential additions (not currently implemented):

- Use nearest-neighbor matching- ✨ Mask area statistics (track size evolution)

- Extract mask at hourly track time- ✨ Spatial variance within masks

- Find nearest model time for variable data- ✨ Multiple mask files for ensemble analysis

- ✨ Parallel processing across date ranges

**Step 3: Extract statistics**

- For each track-time combination:## Contact

  - Get mask cells from hourly mask file

  - Extract variable data from nearest model timeAuthor: Laura Paccini

  - Calculate statistics over mask cellsLast Updated: November 2025


---

## Output Format

Results saved as parquet files:

### File Naming
```
<output_dir>/<variable>_stats_<variable>_<pressure_info>.parquet
```

**Examples:**
- `tas_stats_tas.parquet` (2D variable)
- `hus_stats_hus_850hPa.parquet` (3D single level)
- `omega_stats_omega_avg850-500-300hPa.parquet` (3D averaged levels)

### DataFrame Columns

- `track_id` - MCS track identifier
- `time_idx` - Time index within track
- `data_time` - Actual timestamp
- `time_offset_hours` - Hours since track initiation
- `mean` - Mean value within mask
- `median` - Median value within mask
- `min` - Minimum value within mask
- `max` - Maximum value within mask
- `std` - Standard deviation within mask
- `count` - Total number of cells in mask
- `num_valid` - Number of non-NaN cells

**Note:** No `radius` column (mask defines area)

---

## Command-Line Arguments

### Required Arguments
```bash
--catalog_model       # Model name (e.g., "scream_ne120")
--catalog_params      # JSON params (e.g., '{"zoom": 8, "time": "PT3H"}')
--trackfile           # Path to MCS track NetCDF file
--mask_file           # Path to MCS mask zarr file
--output_dir          # Output directory
--variables           # Variable names (space-separated)
```

### Key Optional Arguments
```bash
--model_time_freq "3H"              # Model output frequency
--batch_size 50                     # Batch size for mask loading
--pressure_levels "850,500,300"     # Pressure levels (hPa) for 3D vars
--convert_wa_to_omega               # Convert wa → omega
--convert_omega_to_wa               # Convert omega → wa
--date_ranges "2020-01-01 2020-12-31"  # Date range filtering
--min_lat -30 --max_lat 30          # Spatial filtering
```

### Full Argument List
See `python get_env_vars_from_masks.py --help` for complete options.

---

## Model-Specific Configuration

### SCREAM
```bash
CATALOG_MODEL="scream_ne120"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'  # 2D data
# For 3D: '{"zoom": 8, "time": "PT6H", "time_method": "inst"}'
MODEL_TIME_FREQ="3H"  # or "6H" for 3D
```

### ICON
```bash
CATALOG_MODEL="icon_d3hp003"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"
```

### IFS
```bash
CATALOG_MODEL="ifs"
CATALOG_PARAMS='{"zoom": 8, "time": "PT1H"}'
MODEL_TIME_FREQ="1H"
```
**Note:** IFS dimension names are automatically fixed by `env_extraction_utils.py`

### UM
```bash
CATALOG_MODEL="um_glm_n2560_RAL3p3"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"
```

### NICAM
```bash
CATALOG_MODEL="nicam_d3hp003"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"
```

---

## Performance Optimization

### Memory-Efficient Small-Batch Processing

The script uses a small-batch approach to minimize memory usage:

1. **Load masks in batches** of unique times (default: 50 times per batch)
2. **Process all tracks** at those times
3. **Move to next batch** and repeat

This amortizes I/O overhead while keeping memory usage low.

### Batch Size Configuration
```bash
--batch_size 50   # Default: good balance
--batch_size 100  # More memory, fewer I/O calls
--batch_size 25   # Less memory, more I/O calls
```

### Performance Tips
1. **Batch size:** Increase if you have memory, decrease if OOM
2. **Date ranges:** Split large datasets into monthly chunks
3. **Variables:** Process multiple in one run (catalog loaded once)
4. **Spatial filtering:** Restrict lat/lon to region of interest

---

## Common Issues and Solutions

### Time Mismatch
**Problem:** Tracks don't align with model times

**Solutions:**
- Verify `MODEL_TIME_FREQ` matches actual model output
- Check catalog `time` parameter (PT3H vs PT6H)
- Use `time_method="inst"` for instantaneous 3D data

### Missing Variables
**Problem:** Variable not found in dataset

**Solutions:**
- Check variable name in catalog documentation
- For sfcWind: Ensure `uas` and `vas` are in catalog
- For 3D: Verify pressure dimension exists

### Empty Results
**Problem:** No statistics extracted

**Possible causes:**
- Mask file doesn't contain track IDs from track file
- No spatial/temporal overlap between tracks and model data
- Track IDs in mask don't match track file IDs

**Debug steps:**
1. Check track IDs in track file: `ncdump -v tracks trackfile.nc`
2. Check mask values: Look at unique values in `mcs_mask`
3. Verify time overlap between mask and model data
4. Confirm spatial filtering isn't excluding all tracks

### Mask Loading Errors
**Problem:** Cannot load mask file

**Solutions:**
- Verify zarr file structure: `python -c "import xarray as xr; print(xr.open_zarr('mask.zarr'))"`
- Check that `mcs_mask` variable exists
- Ensure dimensions are `(time, cell)` for HEALPix

---

## Technical Details

### Utility Functions (from `env_extraction_utils.py`)

The script uses shared utilities:
- **Time conversion:** Handle cftime objects
- **Pressure handling:** Auto-detect Pa vs hPa, normalize levels
- **Vertical velocity:** Convert wa ↔ omega using ω = -ρgw
- **Model fixes:** Standardize IFS and other model dimension names
- **Surface wind:** Compute sfcWind = √(uas² + vas²)

### Mask Cell Extraction

For each track at each time:
1. Load mask slice for that time
2. Find all cells where `mask == track_id`
3. Extract variable values at those cells
4. Calculate statistics (mean, median, std, etc.)
5. Handle NaN values appropriately

### Statistics Calculation

For each mask area:
- **mean, median, min, max, std:** Computed over valid (non-NaN) cells
- **count:** Total cells in mask (including NaN)
- **num_valid:** Number of non-NaN cells used

If all cells are NaN, statistics are set to NaN.

---

## Comparison with Circular Extraction

### When to Use Mask-Based Extraction
✅ Need exact MCS boundaries  
✅ Studying internal MCS structure  
✅ Have mask files available  
✅ Don't need pre-convective period  

### When to Use Circular Extraction
✅ Need pre-convective environment (24h before)  
✅ Want multiple spatial scales (radii)  
✅ No mask files available  
✅ Standard environmental analysis  

**For most environmental studies:** Use circular extraction (`get_env_vars.py`)  
**For MCS-specific studies:** Use mask-based extraction (`get_env_vars_from_masks.py`)

---

## Future Enhancements

Potential additions (not currently implemented):
- ✨ Mask area statistics (track size evolution)
- ✨ Spatial variance within masks
- ✨ Multiple mask files for ensemble analysis
- ✨ Pre-convective period using initial position
- ✨ Parallel processing across date ranges

---

## Example Shell Script

Complete example for SCREAM:

```bash
#!/bin/bash
#SBATCH --job-name=mask_extract
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --constraint=cpu
#SBATCH --qos=debug

# Configuration
CATALOG_MODEL="scream_ne120"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"

TRACKFILE="/path/to/mcs_tracks.nc"
MASK_FILE="/path/to/mcs_masks.zarr"
OUTPUT_DIR="/path/to/output"

VARIABLES=("tas" "huss" "prw" "sfcWind")
DATE_RANGES=("2020-01-01 2020-12-31")

# Run extraction
python get_env_vars_from_masks.py \
  --catalog_model "$CATALOG_MODEL" \
  --catalog_params "$CATALOG_PARAMS" \
  --trackfile "$TRACKFILE" \
  --mask_file "$MASK_FILE" \
  --output_dir "$OUTPUT_DIR" \
  --variables "${VARIABLES[@]}" \
  --model_time_freq "$MODEL_TIME_FREQ" \
  --date_ranges "${DATE_RANGES[@]}" \
  --batch_size 50
```

---

## Support

For questions or issues:
1. Review this documentation
2. Check example scripts: `run_get_env_vars_from_masks_*.sh`
3. Examine log files in `logfiles/` directory
4. Refer to main `README.md` for general guidance

---

**See also:**
- `README.md` - Main documentation for all extraction approaches
- `README_3D_VARIABLES.md` - Details on 3D variables and omega conversion
- `env_extraction_utils.py` - Source code for utility functions
