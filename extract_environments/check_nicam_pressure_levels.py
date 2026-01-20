"""
Check data availability at different pressure levels in NICAM wind shear data

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import sys
import glob

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

# Configuration
PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/NICAM"
PRECOMPUTED_PATTERN = "nicam_gl11_wind_shear_hp8_6H"

print("="*80)
print("CHECKING NICAM PRESSURE LEVEL DATA AVAILABILITY")
print("="*80)

# Find all files
pattern_glob = f"{PRECOMPUTED_DIR}/{PRECOMPUTED_PATTERN}.*.nc"
files_to_load = sorted(glob.glob(pattern_glob))

print(f"\nLoading {len(files_to_load)} files from {PRECOMPUTED_DIR}...")
sys.stdout.flush()

# Open files
ds = xr.open_mfdataset(files_to_load, combine='by_coords')
ds = ds.pipe(egh.attach_coords, signed_lon=True)
ds = ds.assign_coords(time=convert_time(ds.time.values))

print(f"Dataset loaded:")
print(f"  Time steps: {len(ds.time)}")
print(f"  Variables: {list(ds.data_vars)}")
print()

# Check both low_shear and deep_shear
for var_name in ['low_shear_magnitude', 'deep_shear_magnitude']:
    print("="*80)
    print(f"ANALYZING: {var_name}")
    print("="*80)
    
    var_data = ds[var_name]
    print(f"Shape: {var_data.shape}")
    
    # Load a sample (first 10 time steps)
    print(f"\nLoading first 10 time steps into memory...")
    sys.stdout.flush()
    sample = var_data.isel(time=slice(0, 10)).compute()
    
    # Check NaN pattern
    nan_count = np.isnan(sample.values).sum()
    total_count = sample.size
    
    print(f"\nSample (10 time steps) NaN statistics:")
    print(f"  Total values:     {total_count:,}")
    print(f"  NaN values:       {nan_count:,}")
    print(f"  Valid values:     {(total_count - nan_count):,}")
    print(f"  NaN percentage:   {100 * nan_count / total_count:.2f}%")
    
    # Check spatial pattern (which cells have NaNs)
    nan_per_cell = np.isnan(sample.values).sum(axis=0)
    always_nan = (nan_per_cell == 10).sum()
    sometimes_nan = ((nan_per_cell > 0) & (nan_per_cell < 10)).sum()
    never_nan = (nan_per_cell == 0).sum()
    
    print(f"\nSpatial NaN pattern (across 10 time steps):")
    print(f"  Cells ALWAYS NaN (10/10 times): {always_nan:,} ({100*always_nan/sample.shape[1]:.2f}%)")
    print(f"  Cells SOMETIMES NaN:            {sometimes_nan:,} ({100*sometimes_nan/sample.shape[1]:.2f}%)")
    print(f"  Cells NEVER NaN:                {never_nan:,} ({100*never_nan/sample.shape[1]:.2f}%)")
    
print("\n" + "="*80)
print("EXPLANATION")
print("="*80)

print("""
Based on the pressure levels used:

LOW-SHEAR (400 hPa - 1000 hPa):
  - Uses 1000 hPa level (surface/near-surface)
  - Problem: 1000 hPa is AT or BELOW surface over elevated terrain
  - Result: Massive NaN percentage (~59%) over mountains/land

DEEP-SHEAR (100 hPa - 850 hPa):
  - Uses 850 hPa level (well above surface)
  - Both 850 and 100 hPa are in free atmosphere
  - Result: Much lower NaN percentage (~4.5%) - only boundary regions

RECOMMENDATION:
===============
Change low-shear definition to use a higher lower-level:
  - Option 1: 925 hPa - 500 hPa (standard low-level shear)
  - Option 2: 850 hPa - 500 hPa (even more reliable)
  
Both options avoid the problematic 1000 hPa level that's below ground
over much of the globe.

To fix this, edit compute_wind_shear.py:
  Change: low_shear_levels_hPa = [1000, 400]
  To:     low_shear_levels_hPa = [925, 500]  # or [850, 500]
  
Then regenerate the pre-computed wind shear files.
""")

print("="*80)
