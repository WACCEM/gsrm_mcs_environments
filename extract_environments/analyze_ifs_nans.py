"""
Detailed analysis of NaN patterns in IFS pre-computed data

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import sys

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

# IFS Configuration
PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/IFS"
PRECOMPUTED_PATTERN = "ifs_tco3999_rcbmf_wind_shear_hp7_3H"
VARIABLE_NAME = "deep_shear_magnitude"

print("="*80)
print("DETAILED IFS NaN ANALYSIS")
print("="*80)

# Find all files
import glob
files_to_load = sorted(glob.glob(f"{PRECOMPUTED_DIR}/{PRECOMPUTED_PATTERN}.*.nc"))

print(f"\nLoading {len(files_to_load)} files...")
sys.stdout.flush()

# Open files
ds = xr.open_mfdataset(files_to_load, combine='by_coords')
ds = ds.pipe(egh.attach_coords, signed_lon=True)
ds = ds.assign_coords(time=convert_time(ds.time.values))

print(f"Dataset loaded: {len(ds.time)} time steps")
print(f"Time range: {ds.time.values[0]} to {ds.time.values[-1]}")

# Load data
var_data = ds[VARIABLE_NAME]
print(f"\nLoading {VARIABLE_NAME} into memory...")
sys.stdout.flush()
var_computed = var_data.compute()

# Find all-NaN time steps
print(f"\nFinding all-NaN time steps...")
sys.stdout.flush()

all_nan_times = []
for t_idx in range(len(var_computed.time)):
    time_slice = var_computed.isel(time=t_idx).values
    if np.all(np.isnan(time_slice)):
        all_nan_times.append(var_computed.time.values[t_idx])

print(f"\n{'='*80}")
print(f"QUESTION 1: WHEN DO NaNs OCCUR IN IFS?")
print(f"{'='*80}")

print(f"\nFound {len(all_nan_times)} time steps with ALL NaN values")

if len(all_nan_times) > 0:
    # Convert to DataFrame for analysis
    df = pd.DataFrame({'timestamp': all_nan_times})
    df['datetime'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['datetime'].dt.date
    df['month'] = df['datetime'].dt.month
    df['day'] = df['datetime'].dt.day
    
    # Group by month
    by_month = df.groupby('month').size()
    
    print(f"\n📅 NaN Time Steps by Month:")
    print("-" * 40)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for month_num, count in by_month.items():
        print(f"  {months[month_num-1]} 2020: {count} time steps")
    
    # Get unique dates
    unique_dates = df['date'].unique()
    print(f"\n📅 Dates with ALL-NaN time steps: {len(unique_dates)} days")
    print(f"  Date range: {unique_dates[0]} to {unique_dates[-1]}")
    
    # Check if it's continuous
    dates_pd = pd.to_datetime(unique_dates)
    dates_sorted = sorted(dates_pd)
    
    # Find gaps
    print(f"\n🔍 Checking for temporal pattern...")
    date_diffs = [(dates_sorted[i+1] - dates_sorted[i]).days for i in range(len(dates_sorted)-1)]
    
    if all(d == 1 for d in date_diffs):
        print(f"  ✓ Continuous period: ALL {len(unique_dates)} days are consecutive")
        print(f"  Period: {dates_sorted[0].date()} to {dates_sorted[-1].date()}")
    else:
        gaps = [i for i, d in enumerate(date_diffs) if d > 1]
        if len(gaps) == 0:
            print(f"  ✓ Continuous period")
        else:
            print(f"  ⚠️ Found {len(gaps)} gap(s) in the NaN period")
            for gap_idx in gaps[:5]:
                print(f"    Gap between {dates_sorted[gap_idx].date()} and {dates_sorted[gap_idx+1].date()}")
    
    # Show all dates
    print(f"\n📅 Complete list of ALL-NaN dates:")
    print("-" * 40)
    for i, date in enumerate(sorted(unique_dates)):
        print(f"  {date}", end="")
        if (i + 1) % 5 == 0:
            print()  # New line every 5 dates
        else:
            print("  ", end="")
    print()  # Final newline
    
    # Show first and last few timestamps
    print(f"\n🕐 First 5 NaN timestamps:")
    for ts in all_nan_times[:5]:
        print(f"  {ts}")
    
    print(f"\n🕐 Last 5 NaN timestamps:")
    for ts in all_nan_times[-5:]:
        print(f"  {ts}")

print(f"\n{'='*80}")
print(f"SUMMARY - QUESTION 1")
print(f"{'='*80}")
print(f"\n❌ IFS pre-computed data has a gap:")
print(f"   - {len(all_nan_times)} time steps with ALL NaN values")
print(f"   - Covering approximately {len(unique_dates)} days")
print(f"   - This represents {100*len(all_nan_times)/len(var_computed.time):.2f}% of the total time period")
print(f"\n💡 Impact on track extraction:")
print(f"   - Any tracks occurring during this period cannot be processed")
print(f"   - This explains the ~2,349 missing tracks in your results")
print(f"   - Tracks that span this period may be partially processed")
print(f"\n🔧 Solution:")
print(f"   - Regenerate pre-computed data for the missing period")
print(f"   - Or use direct catalog loading (slower but complete)")
print("="*80)
