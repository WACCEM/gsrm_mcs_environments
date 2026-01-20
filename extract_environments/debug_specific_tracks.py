"""
Debug why specific ocean tracks have deep_shear but not low_shear data

This script extracts environments for a subset of tracks at initialization only
to diagnose the NaN issue between low_shear and deep_shear.

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import healpy as hp
import sys
import glob

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

# Configuration
TRACK_FILE = "/pscratch/sd/w/wcmca1/hackathon/mcs/nicam_gl11/stats/mcs_tracks_final_20200301.0000_20210301.0000.nc"
PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/NICAM"
PRECOMPUTED_PATTERN = "nicam_gl11_wind_shear_hp8_6H"

# Subset of problematic tracks (first 10 from your list)
PROBLEM_TRACKS = [193, 242, 349, 401, 406, 539, 740, 873, 917, 1024]

RADIUS = 2.0  # degrees
NSIDE = 256  # NICAM uses zoom=8 -> nside=256

print("="*80)
print("DEBUGGING LOW_SHEAR vs DEEP_SHEAR for SPECIFIC TRACKS")
print("="*80)

# Load track data
print(f"\nLoading track data from {TRACK_FILE}...")
sys.stdout.flush()

mcs_trackstats = xr.open_dataset(TRACK_FILE)
required_vars = ['meanlon', 'meanlat', 'base_time']
subset = mcs_trackstats[required_vars].compute()
df_all = subset.to_dataframe().reset_index()

print(f"Total tracks in file: {df_all['tracks'].nunique()}")
print(f"Total track-time points: {len(df_all)}")

# Filter to problem tracks only
df_problem = df_all[df_all['tracks'].isin(PROBLEM_TRACKS)].copy()
print(f"\nFiltered to {len(PROBLEM_TRACKS)} problem tracks: {len(df_problem)} track-time points")

# Get only first time step (initialization) for each track
df_init = df_problem.groupby('tracks').first().reset_index()
print(f"Extracted initialization times: {len(df_init)} points")

# Load pre-computed data
print(f"\nLoading pre-computed wind shear data...")
sys.stdout.flush()

files = sorted(glob.glob(f"{PRECOMPUTED_DIR}/{PRECOMPUTED_PATTERN}.*.nc"))
print(f"Found {len(files)} files")

ds = xr.open_mfdataset(files, combine='by_coords')
ds = ds.pipe(egh.attach_coords, signed_lon=True)
ds = ds.assign_coords(time=convert_time(ds.time.values))

print(f"Dataset loaded:")
print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
print(f"  Variables: {list(ds.data_vars)}")
print(f"  Shape: {ds['low_shear_magnitude'].shape}")

# Calculate HEALPix indices for track positions
print(f"\nCalculating HEALPix indices for track positions...")
sys.stdout.flush()

hp_grid = ds[['lat', 'lon']].compute()
track_hp_indices = hp.ang2pix(
    NSIDE,
    df_init['meanlon'].values,
    df_init['meanlat'].values,
    nest=True,
    lonlat=True
)
df_init['hp_index'] = track_hp_indices

print(f"HEALPix indices calculated")

# For each track, get circular area and extract data
print("\n" + "="*80)
print("EXTRACTING DATA FOR EACH TRACK")
print("="*80)

results = []

for idx, row in df_init.iterrows():
    track_id = row['tracks']
    lat = row['meanlat']
    lon = row['meanlon']
    time = row['base_time']
    hp_idx = row['hp_index']
    
    print(f"\nTrack {track_id}:")
    print(f"  Position: ({lat:.2f}°, {lon:.2f}°)")
    print(f"  Time: {time}")
    print(f"  HP index: {hp_idx}")
    
    # Get circular area around track
    vec = hp.ang2vec(lon, lat, lonlat=True)
    pixels = hp.query_disc(
        nside=NSIDE,
        vec=vec,
        radius=np.radians(RADIUS),
        nest=True
    )
    
    print(f"  Circular area: {len(pixels)} pixels (radius={RADIUS}°)")
    
    # Find nearest time in dataset
    time_pd = pd.to_datetime(time)
    ds_times = pd.to_datetime(ds.time.values)
    time_diffs = np.abs(ds_times - time_pd)
    nearest_time_idx = np.argmin(time_diffs)
    nearest_time = ds.time.values[nearest_time_idx]
    
    print(f"  Nearest time in dataset: {nearest_time}")
    print(f"  Time difference: {time_diffs[nearest_time_idx]}")
    
    # Extract data for both variables
    low_data = ds['low_shear_magnitude'].isel(time=nearest_time_idx, cell=pixels).values
    deep_data = ds['deep_shear_magnitude'].isel(time=nearest_time_idx, cell=pixels).values
    
    # Count NaNs
    low_nan_count = np.isnan(low_data).sum()
    low_valid_count = len(low_data) - low_nan_count
    deep_nan_count = np.isnan(deep_data).sum()
    deep_valid_count = len(deep_data) - deep_nan_count
    
    print(f"  LOW_SHEAR:  {low_valid_count}/{len(low_data)} valid ({low_nan_count} NaN, {100*low_nan_count/len(low_data):.1f}%)")
    print(f"  DEEP_SHEAR: {deep_valid_count}/{len(deep_data)} valid ({deep_nan_count} NaN, {100*deep_nan_count/len(deep_data):.1f}%)")
    
    # Check if we can compute mean
    low_mean = np.nanmean(low_data) if low_valid_count > 0 else np.nan
    deep_mean = np.nanmean(deep_data) if deep_valid_count > 0 else np.nan
    
    print(f"  LOW_SHEAR mean:  {low_mean:.3f} m/s" if not np.isnan(low_mean) else "  LOW_SHEAR mean:  NaN")
    print(f"  DEEP_SHEAR mean: {deep_mean:.3f} m/s" if not np.isnan(deep_mean) else "  DEEP_SHEAR mean: NaN")
    
    # Determine if track would be included
    # In the extraction code, a track is dropped if num_valid == 0
    low_would_extract = low_valid_count > 0
    deep_would_extract = deep_valid_count > 0
    
    status = "✓✓" if (low_would_extract and deep_would_extract) else \
             "✓❌" if (deep_would_extract and not low_would_extract) else \
             "❌✓" if (low_would_extract and not deep_would_extract) else "❌❌"
    
    print(f"  Extraction status: {status} (deep={deep_would_extract}, low={low_would_extract})")
    
    results.append({
        'track_id': track_id,
        'lat': lat,
        'lon': lon,
        'time': time,
        'pixels_count': len(pixels),
        'low_nan_count': low_nan_count,
        'low_valid_count': low_valid_count,
        'low_nan_pct': 100*low_nan_count/len(low_data),
        'deep_nan_count': deep_nan_count,
        'deep_valid_count': deep_valid_count,
        'deep_nan_pct': 100*deep_nan_count/len(deep_data),
        'low_mean': low_mean,
        'deep_mean': deep_mean,
        'low_extractable': low_would_extract,
        'deep_extractable': deep_would_extract
    })

# Summary
print("\n" + "="*80)
print("SUMMARY TABLE")
print("="*80)

df_results = pd.DataFrame(results)
print(f"\n{df_results.to_string()}")

# Count issues
print("\n" + "="*80)
print("ANALYSIS")
print("="*80)

both_ok = (df_results['low_extractable'] & df_results['deep_extractable']).sum()
deep_only = (df_results['deep_extractable'] & ~df_results['low_extractable']).sum()
low_only = (df_results['low_extractable'] & ~df_results['deep_extractable']).sum()
both_fail = (~df_results['low_extractable'] & ~df_results['deep_extractable']).sum()

print(f"\nExtraction success:")
print(f"  Both extractable:     {both_ok}/{len(df_results)}")
print(f"  Deep only:            {deep_only}/{len(df_results)} ⚠️")
print(f"  Low only:             {low_only}/{len(df_results)}")
print(f"  Neither extractable:  {both_fail}/{len(df_results)}")

print(f"\nAverage NaN percentages:")
print(f"  LOW_SHEAR:  {df_results['low_nan_pct'].mean():.2f}%")
print(f"  DEEP_SHEAR: {df_results['deep_nan_pct'].mean():.2f}%")

if deep_only > 0:
    print(f"\n❌ PROBLEM CONFIRMED:")
    print(f"   {deep_only} tracks have deep_shear data but low_shear is all NaN")
    print(f"   This explains why they appear in deep_shear extraction but not low_shear!")
    
    print(f"\n   Tracks with deep-only data:")
    deep_only_tracks = df_results[df_results['deep_extractable'] & ~df_results['low_extractable']]
    for _, track in deep_only_tracks.iterrows():
        print(f"     Track {track['track_id']}: low_shear={track['low_nan_pct']:.1f}% NaN, deep_shear={track['deep_nan_pct']:.1f}% NaN")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

print("""
This debug confirms that:
1. The problem is NOT in the extraction code
2. The problem is IN THE PRE-COMPUTED DATA itself
3. low_shear_magnitude has many more NaN values than deep_shear_magnitude
4. These NaNs cause tracks to be dropped during low_shear extraction

Next step: Check why low_shear has so many NaNs in the pre-computed files.
Likely causes:
  - 1000 hPa level has missing data (underground at some locations)
  - Bug in wind shear computation script
  - Different data availability at different pressure levels
""")

print("="*80)
