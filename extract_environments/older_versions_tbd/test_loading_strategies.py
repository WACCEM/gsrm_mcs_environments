"""
Test different loading strategies for IFS pre-convective data
Using actual IFS data with 6H model frequency
"""
import xarray as xr
import pandas as pd
import numpy as np
import intake
from easygems import healpix as egh
import healpy as hp
import time
import sys

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return np.array([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                        for t in time_array])
    return time_array

print("="*80)
print("TESTING DIFFERENT LOADING STRATEGIES FOR IFS PRE-CONVECTIVE DATA")
print("="*80)

# Load IFS dataset with 6H resampling
print("\n1. Loading IFS dataset and resampling to 6H...")
sys.stdout.flush()
catalog_url = "https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
cat = intake.open_catalog(catalog_url)['online']
ds = cat['ifs_tco3999_rcbmf'](zoom=7).to_dask().pipe(egh.attach_coords, signed_lon=True)
ds = ds.assign_coords(time=convert_time(ds.time.values))

print(f"   Original: {len(ds.time)} time steps")
ds = ds.resample(time="6H").first()
print(f"   After 6H resampling: {len(ds.time)} time steps")

# Apply IFS fixes
if 'value' in ds.dims and 'cell' in ds.dims:
    cell_values = ds.coords['cell'].values
    ds = ds.drop_dims('cell')
    ds = ds.rename({'value': 'cell'})
    ds = ds.assign_coords({'cell': cell_values})
    ds = ds.pipe(egh.attach_coords, signed_lon=True)
    if 'level' in ds.dims:
        ds = ds.rename({'level': 'pressure'})
    vars_to_rename = {}
    var_name_mapping = {'t': 'ta', 'w': 'wa', 'q': 'hus', 'r': 'hur', '2t': 'tas'}
    for old_name, new_name in var_name_mapping.items():
        if old_name in ds.data_vars or old_name in ds.coords:
            vars_to_rename[old_name] = new_name
    if vars_to_rename:
        ds = ds.rename(vars_to_rename)
    print("   IFS model fixes applied")

# Get grid
hp_grid = ds[['lat', 'lon']].compute()
nside = egh.get_nside(hp_grid)

# Load and process track data
print("\n2. Loading and processing track data...")
trackfile = "/pscratch/sd/p/paccini/IFS_mcs_hackathon/ifs_tco3999_rcbmf/stats/mcs_tracks_final_20200101.0000_20210228.2330.nc"
mcs_trackstats = xr.open_dataset(trackfile)
required_vars = ['meanlon', 'meanlat', 'base_time']
subset = mcs_trackstats[required_vars].compute()
df_all = subset.to_dataframe().reset_index()
df_all = df_all.dropna(subset=['meanlat', 'meanlon'])

# Spatial filtering
min_lat = -90 + 5.0
max_lat = 90 - 5.0
spatial_filter = (
    df_all['meanlat'].between(min_lat, max_lat) &
    df_all['meanlat'].notna() &
    df_all['meanlon'].notna()
)
df_spatial = df_all[spatial_filter].copy().reset_index(drop=True)

# Date range filtering
start_date = pd.Timestamp('2020-01-01')
end_date = pd.Timestamp('2021-03-01')
date_filter = (
    (pd.to_datetime(df_spatial['base_time']) >= start_date) & 
    (pd.to_datetime(df_spatial['base_time']) <= end_date)
)
df_filtered = df_spatial[date_filter].copy()

# Subsample to 6H
print("   Subsampling tracks to 6H...")
freq_td = pd.Timedelta('6H')
filtered_rows = []
for track_id, track_group in df_filtered.groupby('tracks'):
    track_group = track_group.sort_values('times')
    base_times = pd.to_datetime(track_group['base_time'].values)
    first_time = base_times.min()
    time_diffs = base_times - first_time
    aligned_mask = (time_diffs % freq_td) == pd.Timedelta(0)
    filtered_rows.append(track_group[aligned_mask])
df_subsampled = pd.concat(filtered_rows, ignore_index=True)
print(f"   After subsampling: {len(df_subsampled)} track-time points")

# Time alignment
print("   Aligning to dataset times...")
dataset_times_pd = pd.to_datetime(ds.time.values)
track_times_pd = pd.to_datetime(df_subsampled['base_time'])
aligned_times = []
for track_time in track_times_pd:
    time_diffs = np.abs(dataset_times_pd - track_time)
    nearest_idx = time_diffs.argmin()
    aligned_times.append(dataset_times_pd[nearest_idx])
df_aligned = df_subsampled.copy()
df_aligned['base_time'] = aligned_times
print(f"   Aligned unique times: {df_aligned['base_time'].nunique()}")

# Get first track positions for pre-convective extraction
first_times = df_aligned.groupby('tracks').first().reset_index()
print(f"   Number of tracks: {len(first_times)}")

# Calculate pixels for pre-convective areas (simplified - just use first 100 tracks for testing)
print("\n3. Setting up pre-convective extraction (using first 100 tracks for testing)...")
test_tracks = first_times.head(100)
RADII = np.array([5.0, 3.5, 2.0])

preconv_pixels = set()
preconv_times_map = {}

for _, track_info in test_tracks.iterrows():
    track_id = track_info['tracks']
    start_time = pd.Timestamp(track_info['base_time'])
    lon = track_info['meanlon']
    lat = track_info['meanlat']
    
    # Get pixel index
    pixel_idx = hp.ang2pix(nside, lon, lat, nest=True, lonlat=True)
    
    # Get pre-convective times (24 hours before, 6H frequency = 4 time steps)
    for hours_back in range(6, 25, 6):  # 6, 12, 18, 24
        preconv_time = start_time - pd.Timedelta(hours=hours_back)
        if preconv_time >= start_date:
            preconv_times_map[(track_id, preconv_time)] = start_time
    
    # Get pixels for all radii
    for radius in RADII:
        vec = hp.ang2vec(lon, lat, lonlat=True)
        pixels = hp.query_disc(nside, vec, np.radians(radius), nest=True, inclusive=True)
        preconv_pixels.update(pixels)

all_preconv_pixels = list(preconv_pixels)
all_preconv_times = sorted(set(preconv_times_map.keys()), key=lambda x: x[1])

# Align pre-convective times to dataset
aligned_preconv_times = []
for track_id, preconv_time in all_preconv_times:
    time_diffs = np.abs(dataset_times_pd - preconv_time)
    nearest_idx = time_diffs.argmin()
    aligned_preconv_times.append(dataset_times_pd[nearest_idx])

unique_preconv_times = sorted(set(aligned_preconv_times))

print(f"   Pre-convective pixels: {len(all_preconv_pixels)}")
print(f"   Pre-convective times (unique): {len(unique_preconv_times)}")
print(f"   Data size: {len(all_preconv_pixels)} × {len(unique_preconv_times)} = {len(all_preconv_pixels) * len(unique_preconv_times):,} elements")

# Select variable (hur at 850 hPa)
print("\n4. Preparing variable (hur at 850 hPa)...")
var_data = ds['hur'].sel(pressure=850.0, method='nearest')
print(f"   Variable shape: {var_data.shape}")
sys.stdout.flush()

# ============================================================================
# TEST 1: CURRENT APPROACH (Time batching with batch_size=500)
# ============================================================================
print("\n" + "="*80)
print("TEST 1: CURRENT APPROACH (Time batching, batch_size=500)")
print("="*80)

start_time = time.time()
time_batch_size = 500
num_batches = (len(unique_preconv_times) + time_batch_size - 1) // time_batch_size

print(f"Loading in {num_batches} batches...")
sys.stdout.flush()

var_subset_dict = {}
for batch_idx in range(num_batches):
    batch_start = time.time()
    start_idx = batch_idx * time_batch_size
    end_idx = min(start_idx + time_batch_size, len(unique_preconv_times))
    time_batch = unique_preconv_times[start_idx:end_idx]
    
    var_batch = var_data.sel(cell=all_preconv_pixels, time=time_batch).compute()
    
    for t in time_batch:
        var_subset_dict[pd.Timestamp(t)] = var_batch.sel(time=t).values
    
    batch_time = time.time() - batch_start
    print(f"  Batch {batch_idx+1}/{num_batches}: {len(time_batch)} times, {batch_time:.2f}s")
    sys.stdout.flush()

test1_time = time.time() - start_time
print(f"Total time: {test1_time:.2f}s")
print(f"Data loaded: {len(var_subset_dict)} time steps")

# ============================================================================
# TEST 2: SINGLE LOAD (Load all at once)
# ============================================================================
print("\n" + "="*80)
print("TEST 2: SINGLE LOAD (Load all times at once)")
print("="*80)

start_time = time.time()
print(f"Loading {len(all_preconv_pixels)} pixels × {len(unique_preconv_times)} times...")
sys.stdout.flush()

try:
    var_single = var_data.sel(cell=all_preconv_pixels, time=unique_preconv_times).compute()
    test2_time = time.time() - start_time
    print(f"Total time: {test2_time:.2f}s")
    print(f"✓ SUCCESS: Single load worked!")
except Exception as e:
    test2_time = None
    print(f"✗ FAILED: {e}")

# ============================================================================
# TEST 3: LARGER TIME BATCHES (batch_size=1000)
# ============================================================================
print("\n" + "="*80)
print("TEST 3: LARGER TIME BATCHES (batch_size=1000)")
print("="*80)

start_time = time.time()
time_batch_size = 1000
num_batches = (len(unique_preconv_times) + time_batch_size - 1) // time_batch_size

print(f"Loading in {num_batches} batches...")
sys.stdout.flush()

var_subset_dict = {}
for batch_idx in range(num_batches):
    batch_start = time.time()
    start_idx = batch_idx * time_batch_size
    end_idx = min(start_idx + time_batch_size, len(unique_preconv_times))
    time_batch = unique_preconv_times[start_idx:end_idx]
    
    var_batch = var_data.sel(cell=all_preconv_pixels, time=time_batch).compute()
    
    for t in time_batch:
        var_subset_dict[pd.Timestamp(t)] = var_batch.sel(time=t).values
    
    batch_time = time.time() - batch_start
    print(f"  Batch {batch_idx+1}/{num_batches}: {len(time_batch)} times, {batch_time:.2f}s")
    sys.stdout.flush()

test3_time = time.time() - start_time
print(f"Total time: {test3_time:.2f}s")

# ============================================================================
# TEST 4: PIXEL BATCHING (Load all times, batch pixels)
# ============================================================================
print("\n" + "="*80)
print("TEST 4: PIXEL BATCHING (Load all times, batch by pixels)")
print("="*80)

start_time = time.time()
pixel_batch_size = 50000
num_pixel_batches = (len(all_preconv_pixels) + pixel_batch_size - 1) // pixel_batch_size

print(f"Loading in {num_pixel_batches} pixel batches...")
sys.stdout.flush()

var_subset_dict = {}
for batch_idx in range(num_pixel_batches):
    batch_start = time.time()
    start_idx = batch_idx * pixel_batch_size
    end_idx = min(start_idx + pixel_batch_size, len(all_preconv_pixels))
    pixel_batch = all_preconv_pixels[start_idx:end_idx]
    
    var_batch = var_data.sel(cell=pixel_batch, time=unique_preconv_times).compute()
    
    batch_time = time.time() - batch_start
    print(f"  Pixel batch {batch_idx+1}/{num_pixel_batches}: {len(pixel_batch)} pixels × {len(unique_preconv_times)} times, {batch_time:.2f}s")
    sys.stdout.flush()

test4_time = time.time() - start_time
print(f"Total time: {test4_time:.2f}s")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("SUMMARY (100 tracks, ~{} pixels, {} times)".format(len(all_preconv_pixels), len(unique_preconv_times)))
print("="*80)
print(f"TEST 1 (Time batching, 500):  {test1_time:.2f}s")
if test2_time:
    print(f"TEST 2 (Single load):          {test2_time:.2f}s  ← {test1_time/test2_time:.1f}× {'FASTER' if test2_time < test1_time else 'SLOWER'}")
else:
    print(f"TEST 2 (Single load):          FAILED")
print(f"TEST 3 (Time batching, 1000):  {test3_time:.2f}s  ← {test1_time/test3_time:.1f}× {'FASTER' if test3_time < test1_time else 'SLOWER'}")
print(f"TEST 4 (Pixel batching):       {test4_time:.2f}s  ← {test1_time/test4_time:.1f}× {'FASTER' if test4_time < test1_time else 'SLOWER'}")

if test2_time and test2_time < test1_time:
    print(f"\n✓ RECOMMENDATION: Use single load (TEST 2) - {test1_time/test2_time:.1f}× faster")
elif test3_time < test1_time:
    print(f"\n✓ RECOMMENDATION: Use larger time batches (TEST 3) - {test1_time/test3_time:.1f}× faster")
elif test4_time < test1_time:
    print(f"\n✓ RECOMMENDATION: Use pixel batching (TEST 4) - {test1_time/test4_time:.1f}× faster")
else:
    print(f"\n⚠ Current approach (TEST 1) is already optimal or all strategies have similar performance")
