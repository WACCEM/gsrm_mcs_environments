"""
Quick check for NaN values in pre-computed wind shear data

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import sys

# Configuration
PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/IFS"
PRECOMPUTED_PATTERN = "ifs_tco3999_rcbmf_wind_shear_hp7_3H"
VARIABLE_NAME = "deep_shear_magnitude"
START_DATE = "2020-01-01"
END_DATE = "2021-03-01"

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

print("="*60)
print("CHECKING PRE-COMPUTED DATA FOR NaN VALUES")
print("="*60)

# Generate list of files
files_to_load = []
current_date = pd.Timestamp(START_DATE)
end_date_ts = pd.Timestamp(END_DATE)

while current_date <= end_date_ts:
    year = current_date.year
    month = current_date.month
    filename = f"{PRECOMPUTED_PATTERN}.{year}{month:02d}.nc"
    filepath = f"{PRECOMPUTED_DIR}/{filename}"
    files_to_load.append(filepath)
    
    # Move to next month
    if month == 12:
        current_date = pd.Timestamp(year + 1, 1, 1)
    else:
        current_date = pd.Timestamp(year, month + 1, 1)

print(f"\nLoading {len(files_to_load)} pre-computed files...")
sys.stdout.flush()

# Open files
ds = xr.open_mfdataset(files_to_load, combine='by_coords')
ds = ds.pipe(egh.attach_coords, signed_lon=True)
ds = ds.assign_coords(time=convert_time(ds.time.values))

# Filter by date range
ds = ds.sel(time=slice(START_DATE, END_DATE))

print(f"Loaded dataset:")
print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
print(f"  Number of time steps: {len(ds.time)}")
print(f"  Variables: {list(ds.data_vars)}")
print(f"  Shape: {ds[VARIABLE_NAME].shape}")
print()

# Check for NaN values
print("="*60)
print("NaN VALUE ANALYSIS")
print("="*60)

var_data = ds[VARIABLE_NAME]
print(f"\nVariable: {VARIABLE_NAME}")
print(f"  Shape: {var_data.shape}")
print(f"  Total values: {var_data.size:,}")

# Compute the data (load into memory)
print(f"\nLoading data into memory...")
sys.stdout.flush()
var_computed = var_data.compute()

# Count NaNs
print(f"Counting NaN values...")
sys.stdout.flush()
nan_mask = np.isnan(var_computed.values)
nan_count = nan_mask.sum()
total_count = var_computed.size

print(f"\nNaN Statistics:")
print(f"  Total values:     {total_count:,}")
print(f"  NaN values:       {nan_count:,}")
print(f"  Valid values:     {(total_count - nan_count):,}")
print(f"  NaN percentage:   {100 * nan_count / total_count:.4f}%")

# Check which time steps have NaNs
print(f"\n" + "="*60)
print("TIME-STEP NaN ANALYSIS")
print("="*60)

times_with_nans = []
all_nan_times = []

print(f"\nChecking all {len(var_computed.time)} time steps...")
sys.stdout.flush()

for t_idx in range(len(var_computed.time)):
    time_slice = var_computed.isel(time=t_idx).values
    nan_in_slice = np.isnan(time_slice).sum()
    total_in_slice = time_slice.size
    
    if nan_in_slice > 0:
        times_with_nans.append((var_computed.time.values[t_idx], nan_in_slice, total_in_slice))
        
        if nan_in_slice == total_in_slice:
            all_nan_times.append(var_computed.time.values[t_idx])
    
    if (t_idx + 1) % 500 == 0:
        print(f"  Processed {t_idx + 1}/{len(var_computed.time)} time steps...")
        sys.stdout.flush()

print(f"\nResults:")
print(f"  Time steps with ANY NaNs:      {len(times_with_nans)}")
print(f"  Time steps with ALL NaNs:      {len(all_nan_times)}")
print(f"  Time steps with NO NaNs:       {len(var_computed.time) - len(times_with_nans)}")

if len(times_with_nans) > 0:
    print(f"\n⚠️  Time steps with NaN values:")
    for i, (time, nan_count, total) in enumerate(times_with_nans[:20]):
        pct = 100 * nan_count / total
        print(f"    {time}: {nan_count:,}/{total:,} ({pct:.2f}%) NaN")
    
    if len(times_with_nans) > 20:
        print(f"    ... and {len(times_with_nans) - 20} more time steps with NaNs")

if len(all_nan_times) > 0:
    print(f"\n⚠️  Time steps with ALL NaN values:")
    for time in all_nan_times[:20]:
        print(f"    {time}")
    if len(all_nan_times) > 20:
        print(f"    ... and {len(all_nan_times) - 20} more")

# Check spatial distribution of NaNs
print(f"\n" + "="*60)
print("SPATIAL NaN ANALYSIS")
print("="*60)

print(f"\nChecking which cells have NaN values...")
sys.stdout.flush()

# For each cell, count how many time steps have NaN
nan_per_cell = np.isnan(var_computed.values).sum(axis=0)  # Sum over time dimension
cells_with_nans = (nan_per_cell > 0).sum()
cells_all_nans = (nan_per_cell == len(var_computed.time)).sum()
total_cells = var_computed.shape[1]

print(f"\nSpatial NaN Statistics:")
print(f"  Total cells:                   {total_cells:,}")
print(f"  Cells with ANY NaNs:           {cells_with_nans:,} ({100*cells_with_nans/total_cells:.2f}%)")
print(f"  Cells with ALL NaNs:           {cells_all_nans:,} ({100*cells_all_nans/total_cells:.2f}%)")
print(f"  Cells with NO NaNs:            {(total_cells - cells_with_nans):,} ({100*(total_cells-cells_with_nans)/total_cells:.2f}%)")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)

if nan_count == 0:
    print("\n✓ No NaN values found in the pre-computed data!")
    print("  The data appears complete and ready for extraction.")
elif nan_count > 0 and len(all_nan_times) == 0:
    print(f"\n⚠️  Found {nan_count:,} NaN values ({100*nan_count/total_count:.4f}%)")
    print("  These are scattered NaNs, not entire missing time steps.")
    print("  This could cause extraction failures for some track positions.")
else:
    print(f"\n❌ PROBLEM IDENTIFIED:")
    print(f"  Found {len(all_nan_times)} time steps with ALL NaN values!")
    print(f"  This will cause extraction to fail for any tracks at these times.")
    print(f"\n  This explains the difference in track counts:")
    print(f"  - Tracks with times in all-NaN periods cannot be processed")
    print(f"  - These tracks are excluded from final statistics")

print("="*60)
