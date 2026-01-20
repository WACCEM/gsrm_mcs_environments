# MCS Environmental Analysis Workflow

This directory contains scripts and notebooks for analyzing environmental conditions around Mesoscale Convective Systems (MCS) in global storm-resolving models and observations.

## Overview

The workflow involves:
1. **Extraction** (via batch scripts): Extract environmental variables around MCS tracks
2. **Filtering** (in notebooks): Apply quality filters to select MCS events of interest
3. **Analysis** (in notebooks): Analyze and visualize environmental conditions

## Directory Structure

```
gsrm_mcs_environments/
├── extract_environments/          # Scripts for data extraction
│   ├── get_env_vars.py           # Main extraction script
│   ├── get_land_fractions.py     # Land fraction computation
│   ├── run_get_env_vars_NICAM.sh # Example batch script for NERSC
│   └── run_get_land_fractions.sh # Example batch script
│
├── analysis/                      # Analysis notebooks and utilities
│   ├── mcs_analysis_utils.py     # Helper functions (NEW)
│   ├── MCS_analysis_workflow_example.ipynb  # Complete workflow example (NEW)
│   ├── analyze_envvars_evolution_example.ipynb
│   ├── compare_mcs_conditions.ipynb
│   ├── compare_mcs_stats_full_filter.ipynb
│   └── df_filtered_mcs_track_ids/ # Filtered track pickle files
```

## Quick Start

### For New Users

Start with **`MCS_analysis_workflow_example.ipynb`** - a comprehensive notebook that demonstrates:
- How to load environmental data (parquet files)
- How to load filtered MCS tracks (pickle files)
- How to match environmental data with filtered tracks
- How to create distribution plots

All complex functions are in `mcs_analysis_utils.py`, keeping the notebook clean and easy to follow.

### Workflow Steps

#### 1. Data Extraction (Run on HPC)

Extract environmental variables around MCS tracks using the batch scripts:

```bash
# Example: Extract environmental variables for NICAM
sbatch run_get_env_vars_NICAM.sh

# Example: Compute land fractions
sbatch run_get_land_fractions.sh
```

**Outputs**:
- Environmental variables: `/path/to/updated_environmental_variables/MODEL_all/VARIABLE/`
- Land fractions: `/path/to/updated_land_fractions/`

#### 2. MCS Track Filtering

The filtering happens in two stages:

**Stage 1: Basic MCS Filtering**

```python
from mcs_analysis_utils import MCS_filter

# Load raw MCS track file
ds_mcs = xr.open_dataset('path/to/mcs_tracks_final_*.nc')

# Apply basic filters (tropical, oceanic, quality checks)
filtered_tracks = MCS_filter(ds_mcs, 
                             ilat=-30, elat=30,  # Tropical
                             min_ini_nonmcs=2)    # First 2 timesteps are non-MCS

# Save
filtered_tracks.to_pickle('df_trop_model_min2.pkl')
```

**Stage 2: Circular Land Fraction Filtering**

```python
from mcs_analysis_utils import load_circular_land_fractions, apply_circular_land_fraction_filter

# Load pre-computed circular land fractions
lf_data = load_circular_land_fractions('/path/to/land_fractions/', ['icon'])

# Apply circular land fraction filter
final_tracks = apply_circular_land_fraction_filter(
    filtered_tracks, 
    lf_data['icon'],
    radius=2,       # Use 2-degree radius
    lf_thresh=0.1   # 10% threshold
)

# Save
final_tracks.to_pickle('with_circular_lffiltered_model_min2_r2.pkl')
```

See `compare_mcs_conditions.ipynb` and `compare_mcs_stats_full_filter.ipynb` for the complete workflow.

**Outputs**: 
- Stage 1: `df_filtered_mcs_track_ids/df_trop_<model>_min2.pkl`
- Stage 2: `df_filtered_mcs_track_ids/with_circular_lffiltered_<model>_min2_r2.pkl`

#### 3. Analysis

Use `MCS_analysis_workflow_example.ipynb` to:
- Load pre-extracted environmental data
- Match with filtered tracks
- Create visualizations

## Key Concepts

### MCS Filtering Criteria

#### Stage 1: Basic MCS Filtering

The `MCS_filter()` function applies these criteria:

- **Tropical**: Initiation between -30°S and 30°N
- **Oceanic**: Land fraction < 10% during lifetime (uses `pf_landfrac` from MCS track file)
- **Quality**: No splits at initiation, no merging
- **MCS definition**: Initial timesteps are non-MCS, stable MCS status, peak rain during MCS

#### Stage 2: Circular Land Fraction Filtering

Additional filtering using **circular land fractions**:

- **Key difference**: Stage 1 uses land fraction within the precipitation feature, Stage 2 uses land fraction within circular areas at fixed radii (2°, 3.5°, 5°)
- **Purpose**: Ensure MCS tracks are in predominantly oceanic environments at the analysis scale
- **Threshold**: `total_land_fraction_track <= 0.1` (10%) at radius = 2°
- **Data source**: Pre-computed using `get_land_fractions.py` script

### Environmental Data Structure

Parquet files contain statistics (mean, median, min, max, std) of environmental variables computed within circular areas around MCS centroids.

Key columns:
- `track_id`: MCS track identifier
- `time_offset_hours`: Hours relative to initiation (negative = pre-convective)
- `radius`: Circular area radius (degrees)
- `mean`, `median`, etc.: Variable statistics

### Time Periods

- **Pre-convective**: -24 to -1 hours before initiation
- **Initiation**: 0 hours
- **Track lifetime**: 0+ hours (through end of track)

### Spatial Scales

Multiple radii capture different scales:
- **5°**: Large-scale environment
- **3.5°**: Meso-scale
- **2°**: Near-MCS environment (most commonly used)

## Data Sources

### Models
- **ICON**: icon_d3hp003
- **SCREAM**: scream_ne120
- **UM**: um_glm_n2560_RAL3p3
- **IFS**: ifs_tco3999_rcbmf
- **NICAM**: nicam_gl11

### Observations
- **IMERGv6**: ERA5 + IMERG v6
- **IMERGv7**: ERA5 + IMERG v7

### Variables

Environmental variables extracted include:
- **Moisture**: PRW, specific humidity (q), relative humidity (RH)
- **Dynamics**: Omega (vertical velocity), wind shear
- **Thermodynamics**: Temperature, equivalent potential temperature

## File Naming Conventions

### Environmental Data (Parquet)
```
<main_dir>/<MODEL_DIR>/<VARIABLE>/mcs_env_<var>_<dates>_<var>_<level>.parquet
```

Examples:
- `ICON_all/prw/mcs_env_prw_20200101_20201231.parquet`
- `SCREAM_all/hur/mcs_env_hur_20190801_20200901_hur_500hPa.parquet`

### Filtered Tracks (Pickle)
```
with_circular_lffiltered_<model>_<criterion>_r<radius>.pkl
```

Examples:
- `with_circular_lffiltered_icon_min2_r2.pkl`
- `with_circular_lffiltered_obs_v7_min2_r2.pkl`

## Utilities Reference

### `mcs_analysis_utils.py`

Key functions:

#### Filtering Functions
- `MCS_filter(ds_mcs, ...)`: Apply comprehensive MCS filtering (Stage 1)
- `load_circular_land_fractions(lf_dir, models)`: Load circular land fraction data
- `apply_circular_land_fraction_filter(df, lf_data, radius, thresh)`: Apply circular LF filter (Stage 2)
- `remove_longdurations(df, ...)`: Remove long-duration tracks (optional Stage 3)

#### Data Loading Functions
- `load_environmental_data(...)`: Load environmental parquet files
- `load_track_data(...)`: Load filtered track pickle files
- `process_all_data(...)`: Match environmental data with tracks

#### Path Management
- `get_env_path(...)`: Find correct file path for model/variable combination

## Customization

### Adding New Variables

1. Extract the variable using `get_env_vars.py` (modify `run_get_env_vars_*.sh`)
2. Add path pattern to `VAR_PATH_PATTERNS` in the notebook
3. Add to `VARIABLES` list
4. (Optional) Add unit conversion to `TRANSFORM_CONFIG`

### Adding New Models

1. Extract data for the new model
2. Add directory mapping to `ENV_MODEL_DIR_MAP`
3. Add model to `TRACK_MODELS` list
4. Add plotting style to `MODEL_STYLES`

### Changing Filter Criteria

Modify parameters in `MCS_filter()`:
- `ilat`, `elat`: Change latitude range
- `min_ini_nonmcs`: Require different number of initial non-MCS timesteps
- `nomerging=True`: Skip merging filters
- `nopeak=True`: Skip peak rain filter

## Tips

1. **Memory Management**: For large datasets, process one model at a time
2. **Performance**: Use the utility functions which include optimizations
3. **Debugging**: Check `raw_env_data` and `raw_track_data` dictionaries if loading fails
4. **Visualization**: Modify `MODEL_STYLES` for consistent colors across all plots

## Citation

If you use this code, please cite:
- The WACCEM hackathon project
- The individual model papers
- PyFLEXTRKR for MCS tracking (Feng et al., 2023)

## Contact

For questions about this workflow:
- Laura Paccini (laura.paccini@pnnl.gov)

## Version History

- **v2.0 (Jan 2026)**: Added `mcs_analysis_utils.py` and comprehensive example notebook
- **v1.0**: Initial analysis scripts
