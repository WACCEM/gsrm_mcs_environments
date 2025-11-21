# Environmental Variable Extraction for MCS Tracks

This directory contains scripts for extracting environmental statistics around Mesoscale Convective System (MCS) tracks from various global storm-resolving model outputs and reanalysis data.

**Author:** Laura Paccini  
**Last Updated:** November 2025

---

## 📁 Overview

The extraction tools support three main approaches:

1. **Circular Area Extraction** - Extract statistics within circular areas around MCS centroids
2. **Mask-Based Extraction** - Extract statistics using actual MCS spatial masks  
3. **ERA5 Extraction** - Extract from ERA5 reanalysis data (two methods: pre-processed boxes or direct zarr)

---

## Quick Start

### For Model Output (HEALPix Grid)

**Standard models (SCREAM, ICON, UM, NICAM):**
```bash
sbatch run_get_env_vars_SCREAM.sh  # or ICON, UM, NICAM
```

**IFS model (requires time-batching approach):**
```bash
sbatch run_get_env_vars_IFS.sh
```

### For Mask-Based Extraction

```bash
sbatch run_get_env_vars_from_masks_SCREAM.sh  # or other models
```

### For ERA5 Data

**Approach 1: Pre-processed boxes (IMERGv6 tracks - legacy):**
```bash
sbatch run_get_stats_era5.sh
```

**Approach 2: Direct zarr file (IMERGv7 or IMERGv6 tracks - recommended):**
```bash
sbatch run_get_env_vars_ERA5_IMERGv7.sh
```

---

## Core Scripts

### Python Scripts

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `get_env_vars.py` | Circular area extraction (standard) | SCREAM, ICON, UM, NICAM, **ERA5 zarr** |
| `get_env_vars_time_batching.py` | Circular area extraction with time batching | **IFS only** (handles large hourly datasets), **ERA5 zarr (large date ranges)** |
| `get_env_vars_from_masks.py` | Mask-based extraction | When you have MCS mask files |
| `get_stats_era5.py` | ERA5 statistics extraction | ERA5 pre-processed boxes (legacy) |
| `env_extraction_utils.py` | Shared utility functions | Called by above scripts |

### Utility Functions (`env_extraction_utils.py`)

Common functions used by all extraction scripts:
- Time conversion and alignment
- Pressure level handling and unit detection (Pa vs hPa)
- Vertical velocity conversions (wa ↔ omega)
- Model-specific fixes (dimension/variable name standardization)
- Surface wind computation from components

### Shell Scripts

Each model has dedicated bash scripts for easy job submission:
- `run_get_env_vars_SCREAM.sh`
- `run_get_env_vars_ICON.sh`
- `run_get_env_vars_IFS.sh`
- `run_get_env_vars_NICAM.sh`
- `run_get_env_vars_um.sh`
- `run_get_env_vars_from_masks_*.sh` (for mask-based extraction)
- `run_get_stats_era5.sh`

---

## Extraction Approaches

### 1. Circular Area Extraction (`get_env_vars.py`)

**What it does:**
- Extracts statistics within circular areas of specified radii around MCS centroids
- Includes both track duration and pre-convective period (24h before initiation)
- Uses HEALPix grid coordinates

**Key Features:**
- Multiple radii support (e.g., 2°, 3°, 5°)
- Pre-convective environmental sampling
- Efficient batched processing
- 2D and 3D variable support
- Pressure level specification and averaging

**When to use:**
- Standard environmental analysis
- Need pre-convective conditions
- Want to compare different spatial scales (multiple radii)
- Working with HEALPix model output

**Example variables:** `tas`, `huss`, `prw`, `hus` (3D), `wa` (3D)

### 2. Time-Batching Approach (`get_env_vars_time_batching.py`)

**What it does:**
- Same as `get_env_vars.py` but optimized for very large datasets
- Loads data in smaller time batches to avoid server errors

**Key Difference:**
- Adds `--time_batch_size` parameter (default: 1000 time steps per batch)
- Prevents 502 Bad Gateway errors from catalog servers

**When to use:**
- **IFS model specifically** (10,201 hourly time steps)
- Other models with very long time series
- When encountering 502/503 HTTP errors

**Not needed for:**
- SCREAM, ICON, UM, NICAM (standard approach works fine)

### 3. Mask-Based Extraction (`get_env_vars_from_masks.py`)

**What it does:**
- Uses actual MCS mask files to define extraction areas
- Each mask contains track IDs indicating which pixels belong to each MCS
- More accurate representation of MCS spatial extent

**Key Features:**
- No radius parameter (mask defines area)
- Track duration only (no pre-convective period)
- Handles hourly masks vs 3H/6H model output
- Time alignment and subsampling

**When to use:**
- Want statistics within actual MCS boundaries
- Have mask files available (zarr format)
- Studying MCS internal structure
- Don't need pre-convective environment

**Limitations:**
- Requires mask files (not always available)
- No pre-convective period
- Track duration only

### 4. ERA5 Extraction

ERA5 reanalysis can be processed using **two different approaches** depending on the track dataset version:

**Approach 1: Pre-processed boxes (`get_stats_era5.py`) - Legacy**

**What it does:**
- Processes ERA5 data pre-extracted in 25×25° boxes around MCS tracks
- Calculates statistics over circular areas (similar to model output)
- Uses IMERGv6-based track dataset

**Input Data:**
- Directory: `/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global`
- Format: NetCDF files with dimensions (tracks, rel_times, y, x)
- Variables: TCWV, VAR_2T, SP, ISHF, rh_850mb, w_850mb, etc.

**Key Differences from Model Output:**
- Uses relative time (`rel_times`) instead of absolute time
- Data pre-extracted around tracks (not global grid)
- Limited to ±3° from track center

**When to use:**
- Legacy IMERGv6 track validation only

**Approach 2: Direct zarr file (`get_env_vars.py`) - RECOMMENDED**

**What it does:**
- Loads ERA5 from global HEALPix zarr file (same as catalog models)
- Can use updated IMERGv7-based track dataset
- Same processing pipeline as SCREAM, ICON, etc.

**Input Data:**
- Zarr file: `/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr`
- Track file (last version): `/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_*.nc`
- Format: HEALPix grid with absolute timestamps
- All standard ERA5 variables available

**Configuration:**
```bash
# In run_get_env_vars_ERA5_IMERGv7.sh
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"
TRACK_FILE="/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
MODEL_TIME_FREQ="3H"
```

**When to use:**
- Current IMERGv7 track analysis
- Comparing model output to ERA5 reanalysis
- Need observationally-constrained environment
- Want same statistics format as model output

---

## Output Format

All scripts produce parquet files with consistent structure:

### Circular Area Extraction Output
```
<output_dir>/<variable>/mcs_env_<variable>_<start>_<end>_<variable>_<pressure_info>.parquet
```

**Columns:**
- `track_id` - MCS track identifier
- `radius` - Circular area radius (degrees)
- `data_time` - Timestamp
- `time_offset_hours` - Hours since track initiation (negative = pre-convective)
- `mean`, `median`, `min`, `max`, `std` - Statistics
- `count` - Total grid cells in area
- `num_valid` - Non-NaN cells used

### Mask-Based Extraction Output
```
<output_dir>/<variable>_stats_<variable>_<pressure_info>.parquet
```

**Columns:** Same as above, except **no `radius` column** (mask defines area)

### ERA5 Output
```
<output_dir>/<variable>/era5_stats_<variable>_<year_start>_<year_end>.parquet
```

**Columns:** Same as circular area extraction

---

## Common Features

### 2D Variables
Surface and column-integrated variables:
- `tas` - Surface air temperature
- `huss` - Surface specific humidity  
- `prw` - Precipitable water
- `hfls`, `hfss` - Latent/sensible heat flux
- `pr` - Precipitation rate

### 3D Variables with Pressure Levels

Specify pressure levels in hPa:
```bash
VARIABLES=("hus")           # Specific humidity
PRESSURE_LEVELS="850"       # Single level
# or
PRESSURE_LEVELS="850,500,300"  # Multiple levels (averaged)
```

**Supported variables:** `ta`, `hus`, `hur`, `ua`, `va`, `wa`

**Output naming:**
- Single level: `_850hPa`
- Multiple levels: `_avg850-500-300hPa`

### Vertical Velocity Conversions

**wa → omega** (vertical velocity to pressure velocity):
```bash
VARIABLES=("wa")
PRESSURE_LEVELS="850"
CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"
```

**omega → wa** (pressure velocity to vertical velocity):
```bash
VARIABLES=("omega")
PRESSURE_LEVELS="850"
CONVERT_OMEGA_TO_WA="--convert_omega_to_wa"
```

### Surface Wind Speed

Automatically computed from components:
```bash
VARIABLES=("sfcWind")  # Computed from uas and vas
```

### Pre-computed Variables

Use pre-processed monthly NetCDF files instead of accessing the catalog directly. Useful for derived variables (e.g., wind shear) or offline-computed diagnostics.

**Basic usage:**
```bash
PRECOMPUTED_DIR="/path/to/precomputed/data"
TIME_RES="PT3H"
VARIABLES=("prw")
```

**Expected file naming:**
```
{model}_{variable}_hp{zoom}_{timeRes}.{YYYYMM}.nc
```

**Examples:**
```
scream_ne120_prw_hp8_PT3H.202003.nc          # Standard: variable in filename
nicam_gl11_wind_shear_hp8_6H.202003.nc       # Custom: different naming
```

**Custom filename pattern** (when variable name differs):
```bash
PRECOMPUTED_DIR="/path/to/wind_shear/NICAM/"
PRECOMPUTED_PATTERN="nicam_gl11_wind_shear_hp8_6H"  # Omit variable name
TIME_RES="PT6H"
VARIABLES=("deep_shear_magnitude")  # Actual variable name in file
```

**How it works:**
- Script loads monthly files covering your date range
- Automatically concatenates and filters to exact dates
- Processes same as catalog data (radii, statistics, etc.)

**Limitations:**
- Only one variable per run (process multiple variables separately)
- Not compatible with 3D pressure level specifications or wa/omega conversions

### Land Fraction Filtering

Filter tracks by land coverage:
```bash
LAND_FRACTION_FILE="/path/to/land_fractions_summary.parquet"
LAND_THRESHOLD=0.1  # Only tracks with <10% land
```

### Spatial Filtering

Restrict to geographic region:
```bash
--min_lat -30 --max_lat 30
--min_lon 0 --max_lon 180
```

### Date Range Processing

**Recommended:** Process full year at once
```bash
DATE_RANGES=("2019-08-01 2020-09-01")
```

**Only split if needed** (memory constraints):
```bash
DATE_RANGES=(
  "2019-08-01 2019-08-31"
  "2019-09-01 2019-09-30"
)
```

---

## Usage Examples

### Example 1: Extract 2D Variables (SCREAM)
```bash
#!/bin/bash
CATALOG_MODEL="scream_ne120"
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
VARIABLES=("tas" "huss" "prw")
RADII="2,3,5"
DATE_RANGES=("2019-08-01 2020-09-01")

python get_env_vars.py \
  --catalog_model "$CATALOG_MODEL" \
  --catalog_params "$CATALOG_PARAMS" \
  --variables "${VARIABLES[@]}" \
  --radii "$RADII" \
  --date_ranges "${DATE_RANGES[@]}"
```

### Example 2: Extract 3D Variable at Specific Pressure Level
```bash
VARIABLES=("hus")
PRESSURE_LEVELS="850"
CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}'
```

### Example 3: Convert Vertical Velocity to Omega
```bash
VARIABLES=("wa")
PRESSURE_LEVELS="850,500,300"  # Average across levels
CONVERT_WA_TO_OMEGA="--convert_wa_to_omega"
CATALOG_PARAMS='{"zoom": 8, "time": "PT6H", "time_method": "inst"}'
```

### Example 4: IFS with Time Batching
```bash
python get_env_vars_time_batching.py \
  --catalog_model "ifs" \
  --catalog_params '{"zoom": 8, "time": "PT1H"}' \
  --time_batch_size 1000 \
  --variables tas huss \
  --date_ranges "2020-01-01 2020-01-31"
```

### Example 5: Mask-Based Extraction
```bash
python get_env_vars_from_masks.py \
  --catalog_model "icon_d3hp003" \
  --catalog_params '{"zoom": 8, "time": "PT3H"}' \
  --mask_file "/path/to/mcs_mask.zarr" \
  --variables tas huss \
  --model_time_freq "3H" \
  --date_ranges "2020-01-01 2020-12-31"
```

### Example 6: ERA5 Statistics (Pre-processed boxes - legacy)
```bash
python get_stats_era5.py \
  --base_dir /global/cfs/cdirs/m1867/zfeng/gpm/mcs_global \
  --output_dir /path/to/output \
  --variables TCWV VAR_2T rh_850mb \
  --year_start 2020 \
  --year_end 2020 \
  --radii "2,3" \
  --time_freq "3H"
```

### Example 7: ERA5 Direct Zarr (IMERGv7 tracks - recommended)
```bash
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

##  Model-Specific Considerations

### SCREAM (`scream_ne120`)
```bash
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"
LAND_FRACTION_VAR="LANDFRAC"
```

### ICON (`icon_d3hp003`)
```bash
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'  # 2D data
# For 3D: '{"zoom": 8, "time": "PT6H", "time_method": "inst"}'
MODEL_TIME_FREQ="3H"  # or "6H" for 3D
```

### IFS
```bash
CATALOG_PARAMS='{"zoom": 8}'  # 
MODEL_TIME_FREQ="3H" #IFS has hourly output but it is suggested to use 3H for 2D and 6H for 3D
# Use get_env_vars_time_batching.py with --time_batch_size 500
```
**Note:** IFS uses different dimension names (auto-fixed by `env_extraction_utils.py`)

### UM (`um_glm_n2560_RAL3p3`)
```bash
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}'
MODEL_TIME_FREQ="3H"
```

### NICAM (`nicam_d3hp003`)
```bash
CATALOG_PARAMS='{"zoom": 8, "time": "PT3H"}' #For 3D, use "time": "PT6H"
MODEL_TIME_FREQ="3H"
```

### ERA5 (Direct zarr file)
```bash
# Use zarr file instead of catalog
ZARR_PATH="/pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr"
ZARR_MODEL_NAME="era5"
MODEL_TIME_FREQ="3H"

# Track file (IMERGv7)
TRACK_FILE="/global/cfs/cdirs/wcm_shr/hk25/mcs/IMERGv7/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"

# For large date ranges, use time batching:
# python get_env_vars_time_batching.py with --time_batch_size 1000
```
**Note:** ERA5 dimension fixes are auto-applied by `env_extraction_utils.py` (renames 'level' to 'pressure')

---

## Additional Documentation

- **`README_mask_extraction.md`** - Detailed guide for mask-based extraction
- **`README_ERA5.md`** - Complete ERA5 data processing guide
- **`README_3D_VARIABLES.md`** - 3D variables and omega conversion details
- **`README_DATE_RANGES.md`** - Date range processing best practices

---

## Directory Structure

```
extract_environments/
├── README.md                          # This file
├── README_*.md                        # Specialized documentation
│
├── get_env_vars.py                    # Standard circular extraction
├── get_env_vars_time_batching.py     # IFS optimized version
├── get_env_vars_from_masks.py        # Mask-based extraction
├── get_stats_era5.py                  # ERA5 statistics
├── env_extraction_utils.py            # Shared utilities
│
├── run_get_env_vars_*.sh              # Model-specific bash scripts
├── run_get_env_vars_from_masks_*.sh   # Mask extraction scripts
├── run_get_stats_era5.sh              # ERA5 script
│
├── logfiles/                          # Job output logs
├── performance_tests/                 # Performance testing scripts
└── older_versions_tbd/                # Archived older versions
```

---

## ⚡ Performance Tips

### Memory Management
- **Full year processing** usually fits in 32-core debug queue
- Split into monthly chunks only if memory constrained
- Use `--time_batch_size` for IFS to prevent server errors

### Processing Time
- **2D variables:** ~15-20 min per variable for full year
- **3D variables:** ~30-40 min per variable (more data)
- **IFS:** Add ~30% overhead for time batching

### Optimization Strategies
1. Process multiple variables in one job (data loaded once)
2. Use full year date ranges when possible
3. Apply spatial filtering to reduce track count
4. Use land fraction filtering for ocean-only analysis

---

## Troubleshooting

### Missing Variables
**Error:** `Variable 'X' not found in dataset`

**Solutions:**
- Check variable name in catalog documentation
- For 3D: Verify `time_method="inst"` in catalog params
- For sfcWind: Ensure `uas` and `vas` are available

### Time Alignment Issues
**Error:** `No matching times found`

**Solutions:**
- Verify `MODEL_TIME_FREQ` matches actual output
- Check catalog `time` parameter (PT3H vs PT6H)
- Ensure track times overlap with model output

### Memory Errors
**Error:** `MemoryError` or `Killed`

**Solutions:**
- Use `get_env_vars_time_batching.py` for IFS
- Split date ranges into smaller chunks
- Reduce number of variables processed simultaneously

### 502/503 HTTP Errors
**Error:** `502 Bad Gateway` or `503 Service Unavailable`

**Solutions:**
- Use `get_env_vars_time_batching.py` with `--time_batch_size 500-1000`
- Reduce time batching size if still occurring
- Check catalog server status

### Empty Results
**Possible causes:**
- No tracks in specified spatial/temporal range
- Mask file doesn't contain track IDs
- Date range doesn't overlap with model output

**Debug steps:**
1. Check track file date range
2. Verify spatial filtering parameters
3. Confirm mask file format (for mask extraction)
4. Check model data availability for date range

---

## Support

For issues or questions:
1. Check relevant README files for detailed guidance
2. Review shell script examples (`run_get_env_vars_*.sh`)
3. Examine log files in `logfiles/` directory
4. Verify configuration against model-specific considerations

---

## Related Scripts

- **`get_land_fractions.py`** - Calculate land fraction along tracks (separate workflow)

---

## Recent Updates

- **November 2025:** Added mask-based extraction capability
- **November 2025:** Consolidated utility functions into `env_extraction_utils.py`
- **October 2025:** Added time-batching approach for IFS
- **October 2025:** Added pre-computed variable support

---

**For detailed usage of specific features, refer to the specialized README files.**
