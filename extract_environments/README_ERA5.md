````markdown
# ERA5 Environmental Statistics Extraction

Extract environmental statistics from ERA5 reanalysis data for MCS tracks. This script processes ERA5 variables that are already extracted in 25×25° boxes centered on track positions and calculates statistics over circular areas for comparison with model output.

**Script:** `get_stats_era5.py`  
**Author:** Laura Paccini  
**Last Updated:** November 2025

---

## Overview

The `get_stats_era5.py` script is specifically designed for ERA5 reanalysis data with a different structure than model output. ERA5 data is pre-extracted in boxes around MCS tracks rather than on a global grid, and uses relative time offsets instead of absolute timestamps.

---

## Quick Start

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

---

## Input Data Structure

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

| Aspect | Model Output | ERA5 |
|--------|-------------|------|
| Input format | HEALPix grid | Regular lat/lon grid (25x25 boxes) |
| Spatial dimension | Extracted from full global grid | Pre-extracted around tracks |
| Time dimension | `base_time` (absolute) | `rel_times` (relative hours) |
| Output column | `time_offset_hours` | `time_offset_hours` (same!) |
| Processing | Calculate circular areas from HEALPix | Calculate circular areas from boxes |
| Radii | Any radius | Limited by 3° box size |

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

- `get_env_vars.py` - Extract environment from model output (HEALPix grid)
- `get_land_fractions.py` - Calculate land fractions for tracks
