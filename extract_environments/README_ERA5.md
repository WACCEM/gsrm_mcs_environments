````markdown
# ERA5 Environmental Statistics Extraction

Extract environmental statistics from ERA5 reanalysis data for MCS tracks. **Two approaches are available** depending on the track dataset version and data format:

## Two Processing Approaches

### Approach 1: Pre-processed ERA5 boxes (IMERGv6 tracks)
**Script:** `get_stats_era5.py`  
**Data format:** ERA5 pre-extracted in 25×25° boxes  
**Track dataset:** IMERGv6-based MCS tracks  
**Use case:** Legacy processing for IMERGv6 track validation

### Approach 2: Direct ERA5 zarr file (IMERGv7 tracks)
**Script:** `get_env_vars.py` or `get_env_vars_time_batching.py`  
**Data format:** Global ERA5 HEALPix zarr file  
**Track dataset:** IMERGv7-based MCS tracks (updated tracking)  
**Use case:** Current recommended approach with updated tracks  
**Zarr file:** `/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr`

**Author:** Laura Paccini  
**Last Updated:** November 2025

---

## Overview

### Approach 1: `get_stats_era5.py` (IMERGv6 tracks)

This script is specifically designed for ERA5 reanalysis data that is **pre-extracted in boxes** around MCS tracks rather than on a global grid, and uses relative time offsets instead of absolute timestamps. This approach uses the **IMERGv6-based track dataset**.

### Approach 2: `get_env_vars.py` with zarr (IMERGv7 tracks)

The general environmental extraction script now supports **direct zarr file loading** for ERA5 global data. This allows using the **updated IMERGv7-based track dataset** with un-processed ERA5 data on the global HEALPix grid. This is the **recommended approach** for new analyses.

---

## Comparison of Approaches

| Aspect | Approach 1: Pre-processed boxes | Approach 2: Direct zarr |
|--------|----------------------------------|-------------------------|
| **Script** | `get_stats_era5.py` | `get_env_vars.py` / `get_env_vars_time_batching.py` |
| **Track dataset** | IMERGv6-based | IMERGv7-based (updated) |
| **Data format** | Pre-extracted 25×25° boxes | Global HEALPix grid |
| **Data location** | `/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global/era5_2d/` | `/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr` |
| **Time dimension** | Relative hours (`rel_times`) | Absolute timestamps (`time`) |
| **Spatial extraction** | From pre-extracted boxes | From global grid (like models) |
| **Variables** | Limited to pre-extracted | All available in zarr |
| **Use case** | Legacy IMERGv6 validation | Current IMERGv7 analysis |
| **Recommended** | For IMERGv6 comparison only | **Yes - for new work** |

---

## Quick Start

### Approach 1: Pre-processed boxes (IMERGv6 tracks)

```bash
# Run with bash script (recommended)
sbatch run_get_stats_era5.sh

# Or run Python directly
python get_stats_era5.py \
  --base_dir /global/cfs/cdirs/m1867/zfeng/gpm/mcs_global \
  --output_dir /path/to/output \
  --variables TCWV VAR_2T \
  --year_start 2020 \
  --year_end 2020 \
  --radii "2,3" \
  --time_freq "3H"
```

### Approach 2: Direct zarr (IMERGv7 tracks) - RECOMMENDED

```bash
# Run with bash script (recommended)
sbatch run_get_env_vars_ERA5_IMERGv7.sh

# Or run Python directly
python get_env_vars.py \
  --zarr_path "/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr" \
  --zarr_model_name "era5" \
  --trackfile /global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc \
  --output_dir /path/to/output \
  --variables prw tas \
  --date_ranges "2019-08-01 2020-09-01" \
  --radii "2,3" \
  --model_time_freq "3H"
```

---

## Approach 2: Direct Zarr with IMERGv7 Tracks (RECOMMENDED)

### Key Differences from Approach 1

1. **Updated tracks:** Uses IMERGv7-based MCS tracking (improved algorithm)
2. **Global data:** ERA5 on full HEALPix grid, not pre-extracted boxes
3. **Unified pipeline:** Same script (`get_env_vars.py`) for all models and observations
4. **More variables:** Access to all ERA5 variables in the zarr file
5. **Absolute time:** Uses actual timestamps, not relative hours

### Input Data

**Track file (IMERGv7):**
```
/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc
```

**ERA5 zarr file:**
```
/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr
```
- **Time resolution:** 3-hourly
- **Spatial resolution:** HEALPix zoom 8 (~13 km)
- **Time coverage:** 2019-01-01 to 2021-12-31
- **Dimensions:** `time`, `cell`, `pressure` (for 3D variables)
- **Available variables:** d2m, hfssd, hur, hus, ie, omega, prw, ps, psl, sstk, ta, tas, u10, ua, v10, va, zg

### Configuration (run_get_env_vars_ERA5_IMERGv7.sh)

```bash
# Track file (IMERGv7)
TRACK_FILE="/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"

# ERA5 zarr file
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"

# Output directory
OUTPUT_DIR="/pscratch/sd/p/paccini/temp/hackathon/updated_environmental_variables/ERA5_IMERGv7"

# Processing parameters
RADII="2,3"  # Circular area radii in degrees
MODEL_TIME_FREQ="3H"  # ERA5 frequency
HOURS_BEFORE_INIT="24"  # Pre-convective period
TIME_BATCH_SIZE="1000"  # Time steps per batch (for large datasets)

# Variables (2D examples)
VARIABLES=("prw" "tas")  # Total column water vapor, surface temperature

# Variables (3D with pressure levels)
VARIABLES=("ta" "hus")  # Temperature, specific humidity
PRESSURE_LEVELS="850,500"  # Extract at 850 and 500 hPa

# Date range
DATE_RANGES=(
  "2019-08-01 2020-09-01"
)
```

### Output Format

Same as other models processed with `get_env_vars.py`:

```
<output_dir>/<variable_name>/era5_stats_<variable_name>_YYYY_YYYY.parquet
```

**DataFrame columns:**
- `track_id` - Track ID from IMERGv7
- `time_idx` - Time index within track
- `base_time` - Absolute timestamp
- `data_time` - Actual data timestamp (nearest to base_time)
- `time_offset_hours` - Hours from track initiation
- `radius` - Circular area radius in degrees
- `mean`, `median`, `min`, `max`, `std` - Statistics within circle
- `count`, `num_valid` - Pixel counts

### Performance Notes

**For large time ranges (>6 months), use `get_env_vars_time_batching.py`:**

This version loads time steps in batches (default 1000) to avoid memory issues and I/O timeouts:

```bash
# In run_get_env_vars_ERA5_IMERGv7.sh, change:
python get_env_vars.py ...  # Default version
# to:
python get_env_vars_time_batching.py ...  # Batched version

# Set batch size
TIME_BATCH_SIZE="1000"  # Larger for 2D, smaller for 3D
```

**Recommended batch sizes:**
- 2D variables: 1000-2000 time steps
- 3D variables: 500-1000 time steps
- Pre-convective data: 1000 (loads all tracks' pre-convective times at once)

### Why Use Approach 2?

1. **Updated tracks:** IMERGv7 has improved MCS detection and tracking
2. **Consistency:** Same processing pipeline as SCREAM, ICON, IFS, etc.
3. **Flexibility:** Easy to add new variables without pre-extraction
4. **Future-proof:** Direct access to source data, not dependent on pre-processing
5. **Model-ready:** Uses model-specific fixes from `env_extraction_utils.py`

---

## Approach 1: Pre-processed Boxes with IMERGv6 Tracks (LEGACY)

### Input Data Structure

**Input Data:**
- **Base directory:** `/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global`
- **Subdirectories:**
  - `era5_2d/` - Single file per variable per year
  - `era5_2d_derived/` - Multiple files (100 tracks each) per year
- **Dimensions:** 
  - `tracks` - Track ID
  - `rel_times` - Time offset in hours (equivalent to `time_offset_hours`)
  - `y`, `x` - Spatial dimensions (25x25 grid)
- **Spatial grid:** 
  - 0.25° resolution
  - Center at (0, 0)
  - Range: -12 to +12 (±3° from track center)

**Available Variables:**
- **era5_2d:** TCWV, VAR_2T, SP, ISHF
- **era5_2d_derived:** rh_850mb, rh_500mb, w_850mb, w_500mb, q_850mb, q_500mb

## Output Format

**Output structure (matches `get_env_vars.py`):**
```
<output_dir>/<variable_name>/era5_stats_<variable_name>_<year_start>_<year_end>.parquet
```

**DataFrame columns:**
- `track_id` - Track ID
- `radius` - Circular area radius in degrees
- `time_offset_hours` - Time offset from track initiation (hours)
- `mean` - Mean value within circle
- `median` - Median value within circle
- `min` - Minimum value within circle
- `max` - Maximum value within circle
- `std` - Standard deviation within circle
- `count` - Total pixels in circle
- `num_valid` - Number of valid (non-NaN) pixels

## Usage

### Basic Usage

Process TCWV for 2020 with 3-hourly frequency:
```bash
sbatch run_get_stats_era5.sh
```

### Shell Script Configuration

Edit `run_get_stats_era5.sh`:

```bash
# Time range
YEAR_START=2020
YEAR_END=2020

# Radii in degrees
RADII="2,3"

# Time frequency - match model output
TIME_FREQ="3H"  # Extract at 3-hourly intervals

# Variables to process
VARIABLES=("TCWV" "VAR_2T")
```

### Python Script Direct Usage

```bash
python get_stats_era5.py \
  --base_dir /global/cfs/cdirs/m1867/zfeng/gpm/mcs_global \
  --output_dir /path/to/output \
  --variables TCWV VAR_2T \
  --year_start 2020 \
  --year_end 2020 \
  --radii "2,3" \
  --time_freq "3H"
```

### With Track Filtering

Create a file with track IDs (one per line):
```bash
echo "12345" > my_tracks.txt
echo "67890" >> my_tracks.txt
```

Then:
```bash
python get_stats_era5.py \
  --base_dir /global/cfs/cdirs/m1867/zfeng/gpm/mcs_global \
  --output_dir /path/to/output \
  --variables TCWV \
  --year_start 2020 \
  --year_end 2020 \
  --radii "2,3" \
  --track_list my_tracks.txt
```

## Examples

### Example 1: Process 2D variables only
```bash
VARIABLES=("TCWV" "VAR_2T" "SP" "ISHF")
```

### Example 2: Process derived variables only
```bash
VARIABLES=("rh_850mb" "rh_500mb" "w_850mb" "w_500mb" "q_850mb" "q_500mb")
```

### Example 3: Process all variables
```bash
VARIABLES=("TCWV" "VAR_2T" "SP" "ISHF" "rh_850mb" "rh_500mb" "w_850mb" "w_500mb" "q_850mb" "q_500mb")
```

### Example 4: Multiple years
```bash
YEAR_START=2019
YEAR_END=2021
```

### Example 5: Match different model frequencies
```bash
# For SCREAM/UM (3-hourly output)
TIME_FREQ="3H"

# For ICON (6-hourly output)
TIME_FREQ="6H"

# For hourly analysis
TIME_FREQ="1H"
```

## Time Frequency Details

**Purpose:** Extract ERA5 statistics at the same temporal resolution as model output for direct comparison.

**How it works:**
- ERA5 data has hourly `rel_times`: -23, -22, -21, ..., 0, 1, 2, ..., 223
- Setting `TIME_FREQ="3H"` extracts only: -21, -18, -15, -12, -9, -6, -3, 0, 3, 6, 9, 12, ...
- Setting `TIME_FREQ="6H"` extracts only: -18, -12, -6, 0, 6, 12, 18, 24, ...

**Benefits:**
1. **Reduced computation:** 3H frequency = 1/3 of calculations, 6H = 1/6
2. **Direct comparison:** ERA5 and model output have same time steps
3. **Consistent statistics:** Same temporal averaging as model output

**Note:** All-NaN time steps (tracks that have ended) are automatically skipped regardless of frequency setting.

## File Organization

**Input files (era5_2d):**
```
/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global/era5_2d/
  mcs_era5_TCWV_20200101.0000_20210101.0000.nc
  mcs_era5_VAR_2T_20200101.0000_20210101.0000.nc
  mcs_era5_SP_20200101.0000_20210101.0000.nc
  mcs_era5_ISHF_20200101.0000_20210101.0000.nc
```

**Input files (era5_2d_derived):**
```
/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global/era5_2d_derived/2020/
  mcs_era5_2D_ENVS_20200101.0000_20210101.0000_t00000.nc  # tracks 0-99
  mcs_era5_2D_ENVS_20200101.0000_20210101.0000_t00100.nc  # tracks 100-199
  ...
  mcs_era5_2D_ENVS_20200101.0000_20210101.0000_t32100.nc  # tracks 32100-32199
```

**Output files:**
```
<output_dir>/
  TCWV/
    era5_stats_TCWV_2020_2020.parquet
  VAR_2T/
    era5_stats_VAR_2T_2020_2020.parquet
  rh_850mb/
    era5_stats_rh_850mb_2020_2020.parquet
```

## Comparison with Model Output (`get_env_vars.py`)

| Aspect | Model Output (Catalog) | ERA5 Approach 1 (Boxes) | ERA5 Approach 2 (Zarr) |
|--------|------------------------|-------------------------|------------------------|
| Script | `get_env_vars.py` | `get_stats_era5.py` | `get_env_vars.py` |
| Track dataset | Various | IMERGv6 | IMERGv7 |
| Input format | HEALPix grid (catalog) | Regular lat/lon (25×25° boxes) | HEALPix grid (zarr) |
| Spatial dimension | Extracted from global grid | Pre-extracted around tracks | Extracted from global grid |
| Time dimension | `base_time` (absolute) | `rel_times` (relative hours) | `base_time` (absolute) |
| Output column | `time_offset_hours` | `time_offset_hours` | `time_offset_hours` |
| Processing | Circular areas from HEALPix | Circular areas from boxes | Circular areas from HEALPix |
| Radii | Any radius | Limited by 3° box size | Any radius |
| Data loading | Via intake catalog | Direct file access | Direct zarr file |

## Notes

1. **Maximum radius:** The input boxes are ±3° from center, so don't use radii > 3°
2. **Recommended radii:** 2° and 3° to match common model output analysis
3. **Track IDs:** ERA5 track IDs should match the MCS tracking database
4. **Time offset:** Negative values = before track initiation, positive = during track lifetime
5. **Multiple years:** Script automatically loads and combines data across years
6. **Memory:** Processing all variables for one year fits in 32 CPU debug queue
7. **Time frequency:** Set to match model output (1H, 3H, 6H) for direct comparison
8. **NaN filtering:** All-NaN time steps are automatically skipped (tracks that have ended)
9. **Fill value filtering:** Fill values (-999.0 in era5_2d_derived) are treated as missing data
10. **Pre-convective period:** All tracks have same pre-convective times (rel_times ≤ 0)
11. **Track duration:** Track lifetime varies; data after track end is filled with NaN or -999.0

## Troubleshooting

**Missing files:**
```
WARNING: File not found: /path/to/file.nc
```
- Check that the year exists in the directory
- Verify variable name is spelled correctly

**No data extracted:**
```
WARNING: No data extracted for <variable>
```
- Variable might not exist in the dataset
- Check if it's in era5_2d vs era5_2d_derived
- All time steps may have been filtered (all NaN or -999.0 fill values)

**Memory issues:**
- Process fewer variables at once
- Process one year at a time
- Use track filtering to reduce data volume

## Related Scripts

- `get_env_vars.py` - Extract environment from model output (HEALPix grid) **- Now supports ERA5 zarr files!**
- `get_env_vars_time_batching.py` - Batched version for large datasets (recommended for ERA5 zarr)
- `get_land_fractions.py` - Calculate land fractions for tracks
- `env_extraction_utils.py` - Shared utilities including ERA5-specific model fixes
- `run_get_env_vars_ERA5_IMERGv7.sh` - Example bash script for ERA5 zarr processing with IMERGv7 tracks
