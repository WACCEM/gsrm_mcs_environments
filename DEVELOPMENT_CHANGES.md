# Development Branch - Change Documentation

**Branch:** `dev`  
**Author:** Laura Paccini  
**Date Range:** October 2025 - January 2026  
**Status:** Work in Progress

This document details the major changes and enhancements made to the main Python scripts in the development branch. Bash scripts are excluded from this documentation.

---

## Table of Contents

1. [Environment Extraction Scripts](#environment-extraction-scripts)
2. [Analysis Tools and Utilities](#analysis-tools-and-utilities)
3. [Pre-processing Scripts](#pre-processing-scripts)
4. [Debugging and Diagnostic Tools](#debugging-and-diagnostic-tools)
5. [Summary of Changes](#summary-of-changes)

---

## Environment Extraction Scripts

### 1. `extract_environments/get_env_vars_from_masks.py` (Modified)

**Purpose:** Extract environmental variables using MCS track masks instead of circular areas.

**Key Changes:**
- Added mask-based extraction approach as alternative to circular area method
- Uses actual MCS masks (mcs_mask variable with track IDs) instead of circular areas
- Handles hourly masks vs 3H/6H model output with temporal alignment
- No pre-convective period extraction (only track duration)
- Optimized memory-efficient chunking for mask files (1 time × all cells per chunk)

**Key Features:**
- `load_mask_file()`: Load mask files with explicit chunking for memory efficiency
- `get_mask_cells_for_track()`: Extract cell indices for specific track IDs at given times
- Batch processing approach for efficient extraction
- Statistics computed: mean, median, min, max, std for masked cells

**Use Cases:**
- When precise MCS boundaries are needed (not just circular approximations)
- For variables that require exact convective system extent
- Alternative validation method for circular area extraction

---

### 2. `extract_environments/get_env_vars_time_batching.py` (Modified)

**Purpose:** Extract environmental variables within circular areas around MCS tracks with optimized batching.

**Major Updates:**
- Enhanced time batching efficiency (similar to `get_land_fractions.py` approach)
- Minimal track metadata access during extraction (no MultiIndex lookups)
- Metadata merged after extraction using simple join operations
- Support for pre-convective period (24 hours before track initiation)
- Better memory management with batch processing

**Key Functions:**
- `convert_time()`: Convert cftime to standard datetime64
- `parse_pressure_levels()`: Parse pressure level strings from command line
- `detect_pressure_units()`: Auto-detect Pa vs hPa in datasets
- `normalize_pressure_levels()`: Convert user-specified levels to match dataset units

**Optimizations:**
- Batched extraction reduces memory overhead
- Pre-convective data collected separately for efficiency
- Supports multiple radii (5.0, 3.5, 2.0 degrees) in single run

**Statistics Extracted:**
- Track duration: statistics at each MCS lifecycle time step
- Pre-convective: 24-hour period before initiation for context

---

### 3. `extract_environments/env_extraction_utils.py` (Modified)

**Purpose:** Common utility functions shared between all extraction scripts.

**Key Utilities Added/Enhanced:**

#### Time and Coordinate Handling:
- `convert_time()`: Convert cftime to standard datetime64 format
- Improved datetime handling across different model outputs

#### Pressure Level Management:
- `parse_pressure_levels()`: Parse pressure levels from bash strings
- `detect_pressure_units()`: Auto-detect Pascals vs hectopascals using median value heuristic
  - Pa: median > 2000 (typical range: 100000-10000 Pa)
  - hPa: median < 2000 (typical range: 1000-100 hPa)
- `normalize_pressure_levels()`: Convert user levels (hPa) to match dataset units

#### Variable Conversions:
- `convert_w_to_omega()`: Convert vertical velocity (w) to pressure velocity (omega)
- `convert_omega_to_w()`: Convert pressure velocity back to vertical velocity
- `compute_surface_wind_speed()`: Calculate wind speed magnitude from u/v components
- `compute_latent_heat_flux()`: Derive latent heat flux from available variables

#### Model-Specific Fixes:
- `apply_model_fixes()`: Unified function to handle dimension/variable name inconsistencies
  - Handles different dimension names (value/cell, level/lev/pressure)
  - Maps variable names across models (t/ta, q/hus, u/ua, v/va)
  - Addresses model-specific quirks

#### Track Processing:
- `subsample_tracks_by_frequency()`: Subsample track timesteps to match model output frequency
- `load_land_fraction_summary()`: Load and filter tracks by land fraction threshold

**Benefits:**
- Centralized functions reduce code duplication
- Consistent handling across circular area and mask-based extraction
- Easier maintenance and debugging

---

### 4. `extract_environments/get_env_vars_from_masks_v1.py` (New)

**Purpose:** Version 1 backup of mask-based extraction script.

**Status:** Development/testing version preserved for reference.

---

### 5. `extract_environments/get_env_vars_from_masks_last.py` (New)

**Purpose:** Latest working version of mask-based extraction before final merge.

**Status:** Backup copy for rollback if needed.

---

## Analysis Tools and Utilities

### 6. `analysis/mcs_analysis_utils.py` (New)

**Purpose:** Comprehensive helper functions for MCS track filtering and environmental data processing.

**Major Components:**

#### MCS Track Filtering (`MCS_filter()`):
Applies comprehensive filtering criteria to MCS tracks:

**Filtering Criteria:**
1. **Split Filter:** MCS do not start with a split (`start_split_cloudnumber` is NaN)
2. **Tropical Filter:** Latitude range constraint (default: -30° to 30°)
3. **Land Fraction:** < 10% land fraction during entire lifetime
4. **Merging Constraints:** 
   - `start_status` = 1 or 2 (not merged at start)
   - `end_status` = 0 or 3 (not merged at end)
5. **Initial Non-MCS Period:** Minimum number of initial non-MCS timesteps (default: 3)
6. **MCS Stability:** Continuous MCS status (sum of mcs_status = mcs_duration)
7. **Peak Rain Timing:** Total rainfall peak occurs during MCS status

**Parameters:**
```python
def MCS_filter(ds_mcs, ilat=-30, elat=30, filter_split=True, 
               min_ini_nonmcs=3, nomerging=False, nopeak=False)
```

**Flexibility:**
- `nomerging=True`: Skip merging filters (criteria iv)
- `nopeak=True`: Skip peak rain filter (criterion vi)
- Customizable latitude range and minimum initial non-MCS period

**Output:**
- Returns filtered DataFrame with track statistics
- Provides count of filtered tracks for each criterion

#### Additional Utilities:
- Track metadata extraction
- Environmental variable matching to filtered tracks
- Data quality checks and validation

**Use Cases:**
- Standardized MCS filtering across all analysis notebooks
- Quality control for track selection
- Reproducible filtering criteria

---

### 7. `analysis/tools_mcs_stats.py` (Modified)

**Purpose:** Tools for MCS statistics analysis and visualization.

**New/Enhanced Functions:**

#### `filter_tracks_by_initiation()`:
Filter MCS tracks based on initiation criteria with fine-grained control.

**Parameters:**
- `min_duration`: Minimum track duration in hours (default: 6)
- `require_split_nan`: Keep only tracks where `start_split_cloudnumber` is NaN
- `require_mcs_status_zero`: Keep only tracks with `mcs_status=0` at initiation

**Features:**
- Progressive filtering with status updates
- Returns DataFrame with only tracks meeting all criteria
- Useful for studying MCS genesis specifically

#### `evolution_by_radius()`:
Plot the evolution of environmental statistics for different radii.

**Key Features:**
- Supports multiple radii or single radius plotting
- Configurable time range relative to initiation
- Statistical variable selection (mean, std, median, etc.)
- Customizable titles and formatting

**Enhancements:**
- Improved handling of multiple track datasets
- Better visualization options
- More robust error handling

---

## Pre-processing Scripts

### 8. `pre_process/compute_wind_shear.py` (Modified)

**Purpose:** Compute wind shear metrics (Low-Shear and Deep-Shear) from HEALPix Zarr data.

**Wind Shear Definitions:**
- **Low-Shear:** 400 hPa - 1000 hPa (magnitude and direction)
- **Deep-Shear:** 850 hPa - 100 hPa (magnitude and direction)

**Key Improvements:**

#### Multi-Model Support:
Handles different models (IFS, SCREAM, NICAM, ICON, UM, ERA5) with varying:
- **Dimension names:** value/cell, level/lev/pressure
- **Variable names:** t/ta, q/hus, u/ua, v/va, w/wa/wap
- **Pressure units:** Pascals vs hectopascals
- **Grid configurations:** Different HEALPix zoom levels

#### Enhanced Functions:
- `convert_time()`: Standardize time formats across models
- `detect_pressure_units()`: Auto-detect Pa vs hPa
- `normalize_pressure_levels()`: Convert pressure levels to match dataset
- `apply_model_fixes()`: Unified dimension/variable name handling

#### Wind Shear Computation:
```python
# Low-Shear: 400 - 1000 hPa
u_shear_low = u_400hPa - u_1000hPa
v_shear_low = v_400hPa - v_1000hPa
magnitude_low = sqrt(u_shear_low² + v_shear_low²)
direction_low = arctan2(v_shear_low, u_shear_low)

# Deep-Shear: 850 - 100 hPa  
u_shear_deep = u_850hPa - u_100hPa
v_shear_deep = v_850hPa - v_100hPa
magnitude_deep = sqrt(u_shear_deep² + v_shear_deep²)
direction_deep = arctan2(v_shear_deep, u_shear_deep)
```

**Output:**
- NetCDF files with wind shear fields
- Variables: `low_shear_magnitude`, `low_shear_direction`, `deep_shear_magnitude`, `deep_shear_direction`
- Resampled to model native temporal frequency (3H or 6H)

**Performance:**
- Chunked processing for memory efficiency
- Monthly file output for manageable sizes
- Progress tracking and timing information

---

## Debugging and Diagnostic Tools

The following scripts were added to diagnose and fix NaN patterns, data coverage issues, and model-specific problems encountered during extraction.

### 9. `extract_environments/analyze_ifs_nans.py` (New)

**Purpose:** Detailed analysis of NaN patterns in IFS pre-computed wind shear data.

**Diagnostic Capabilities:**
- Identifies all-NaN time steps in IFS wind shear data
- Analyzes temporal distribution of missing data
- Helps diagnose why track counts differ between models

**Findings:**
- IFS has ~7% NaN values with 240 all-NaN timesteps
- NaNs are temporally distributed (entire timesteps missing)
- Different pattern from NICAM (spatially distributed NaNs)

**Use Cases:**
- Understanding IFS-specific data gaps
- Validating pre-computed wind shear files
- Troubleshooting extraction failures

---

### 10. `extract_environments/check_all_precomputed_nans.py` (New)

**Purpose:** Check for NaN values in pre-computed wind shear data across all models.

**Features:**
- Systematic checking of IFS, NICAM, SCREAM, ICON, UM datasets
- Identifies both temporal and spatial NaN patterns
- Generates comprehensive reports per model

**Key Function:**
```python
def check_model_nans(model_name, precomputed_dir, 
                     precomputed_pattern, variable_name)
```

**Output Statistics:**
- Total NaN percentage
- Number of all-NaN timesteps
- Number of all-NaN cells
- Spatial vs temporal NaN distribution

**Use Cases:**
- Data quality control before extraction
- Cross-model comparison of data completeness
- Identifying systematic issues

---

### 11. `extract_environments/check_precomputed_nans.py` (New)

**Purpose:** Focused NaN checking for specific model/variable combinations.

**Features:**
- Detailed NaN pattern analysis
- Cell-level and time-level diagnostics
- Visual representation of NaN distribution

---

### 12. `extract_environments/check_nicam_pressure_levels.py` (New)

**Purpose:** Verify NICAM pressure level availability and units.

**Diagnostics:**
- Check available pressure levels in NICAM datasets
- Verify unit consistency (Pa vs hPa)
- Ensure required levels exist for wind shear computation

**Findings:**
- NICAM uses Pa (Pascals) for pressure coordinates
- All required levels (100, 400, 850, 1000 hPa) are available
- Helped fix pressure level conversion issues

---

### 13. `extract_environments/debug_nicam_wind_shear.py` (New)

**Purpose:** Debug NICAM-specific wind shear computation issues.

**Focus Areas:**
- Wind component extraction at specific pressure levels
- Shear magnitude calculations
- Comparison with other models

---

### 14. `extract_environments/debug_specific_tracks.py` (New)

**Purpose:** Debug why specific ocean tracks have deep_shear but not low_shear data.

**Approach:**
- Extract environments for subset of problematic tracks
- Compare low_shear vs deep_shear extraction
- Identify source of discrepancy

**Problem Tracks Analyzed:**
- 193, 242, 349, 401, 406, 539, 740, 873, 917, 1024 (NICAM)

**Key Insights:**
- NaN patterns differ between low-shear (400-1000 hPa) and deep-shear (850-100 hPa)
- Pressure level availability varies by model configuration
- Helped identify missing 1000 hPa data in some models

---

### 15. `extract_environments/compare_datasets_temporal_coverage.py` (New)

**Purpose:** Compare temporal coverage between pre-computed and catalog-loaded data.

**Use Cases:**
- Verify pre-computed wind shear has correct time coverage
- Diagnose why track counts differ between extraction methods
- Ensure temporal alignment between datasets

**Comparisons:**
- Pre-computed files vs intake catalog data
- Model native frequency vs resampled frequency
- Expected vs actual time ranges

---

### 16. `extract_environments/explain_nan_patterns.py` (New)

**Purpose:** Educational script explaining different NaN patterns across models.

**Key Concepts Explained:**

#### NICAM Pattern: Scattered NaNs (~4.5%)
- NaNs spatially localized to specific cells
- Typically land cells or boundary regions
- No all-NaN timesteps
- 95% of cells have valid data at any time

#### IFS Pattern: Temporal NaNs (~7%)
- Entire timesteps with all NaN values (240 timesteps)
- All cells affected during missing periods
- Indicates missing or failed model output

**Educational Value:**
- Helps users understand expected vs problematic NaN patterns
- Guides interpretation of NaN percentages in diagnostics
- Clarifies when NaNs are normal vs when they indicate issues

---

## Summary of Changes

### Major Enhancements

1. **Dual Extraction Methods:**
   - Circular area extraction (enhanced and optimized)
   - Mask-based extraction (new capability)

2. **Improved Model Compatibility:**
   - Unified handling of 6 models (IFS, NICAM, SCREAM, ICON, UM, ERA5)
   - Auto-detection of pressure units
   - Flexible dimension/variable naming

3. **Comprehensive Utilities:**
   - Centralized utility functions (`env_extraction_utils.py`)
   - Standardized MCS filtering (`mcs_analysis_utils.py`)
   - Enhanced analysis tools (`tools_mcs_stats.py`)

4. **Wind Shear Pre-processing:**
   - Production-ready wind shear computation
   - Multi-model support with model-specific fixes
   - Low-shear and deep-shear metrics

5. **Robust Diagnostics:**
   - 8 new debugging/diagnostic scripts
   - NaN pattern analysis across all models
   - Temporal coverage validation
   - Track-specific debugging capabilities

### Code Quality Improvements

- **Documentation:** Comprehensive docstrings for all functions
- **Error Handling:** Better validation and error messages
- **Performance:** Optimized batching and memory management
- **Maintainability:** Reduced code duplication through shared utilities
- **Reproducibility:** Standardized filtering criteria and extraction methods

### Key Metrics

- **246 files** modified/added
- **102,509 insertions**, **10,297 deletions**
- **6 major Python scripts** enhanced
- **8 diagnostic tools** added
- **2 new analysis utilities** created
- **103 successful job logfiles** included

### Testing Status

- ✅ Extraction tested on all 6 models
- ✅ Wind shear computation validated
- ✅ NaN patterns characterized
- ✅ Track filtering criteria verified
- ⚠️ Some edge cases still under investigation
- ⚠️ Full production validation pending

### Known Issues / Future Work

1. **IFS Temporal Gaps:** 240 all-NaN timesteps need investigation
2. **NICAM Low-Shear:** Some tracks missing 1000 hPa data
3. **Performance Optimization:** Further batching improvements possible
4. **Documentation:** Analysis notebooks need final cleanup
5. **Testing:** Comprehensive integration tests needed

---

## File Reference Guide

### Core Extraction Scripts
```
extract_environments/
├── get_env_vars_from_masks.py        # Mask-based extraction
├── get_env_vars_time_batching.py     # Circular area extraction
└── env_extraction_utils.py           # Shared utilities
```

### Pre-processing
```
pre_process/
└── compute_wind_shear.py              # Wind shear computation
```

### Analysis Tools
```
analysis/
├── mcs_analysis_utils.py              # Track filtering utilities
├── tools_mcs_stats.py                 # Statistics and visualization
└── MCS_analysis_workflow_example.ipynb # Complete workflow example
```

### Diagnostic Tools
```
extract_environments/
├── analyze_ifs_nans.py                # IFS NaN analysis
├── check_all_precomputed_nans.py      # Multi-model NaN checking
├── check_precomputed_nans.py          # Single-model NaN checking
├── check_nicam_pressure_levels.py     # NICAM pressure diagnostics
├── debug_nicam_wind_shear.py          # NICAM wind shear debugging
├── debug_specific_tracks.py           # Track-level debugging
├── compare_datasets_temporal_coverage.py # Temporal validation
└── explain_nan_patterns.py            # Educational NaN patterns
```

---

## Usage Examples

### Extract Environmental Variables (Circular Areas)
```bash
python get_env_vars_time_batching.py \
  --model nicam_gl11 \
  --variables tas hus ua va \
  --pressure_levels 850,500,300 \
  --start_date 2020-02-01 \
  --end_date 2021-03-31
```

### Extract Using MCS Masks
```bash
python get_env_vars_from_masks.py \
  --model nicam_gl11 \
  --mask_file /path/to/mcs_masks.zarr \
  --variables tas hus \
  --start_date 2020-02-01
```

### Compute Wind Shear
```bash
python compute_wind_shear.py \
  --model ifs_tco3999_rcbmf \
  --output_dir /path/to/output \
  --year 2020 \
  --month 02
```

### Check Data Quality
```bash
python check_all_precomputed_nans.py
```

---

## Contact & Support

**Author:** Laura Paccini  
**Repository:** WACCEM/gsrm_mcs_environments  
**Branch:** dev  
**Status:** Active Development

For questions or issues, please refer to the analysis README at `analysis/README.md` or examine the example workflow notebook `MCS_analysis_workflow_example.ipynb`.

---

**Last Updated:** January 19, 2026
