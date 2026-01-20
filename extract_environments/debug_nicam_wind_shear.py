"""
Debug NICAM wind shear computation - check actual data at each pressure level

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import intake
import sys

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

print("="*80)
print("DEBUGGING NICAM WIND SHEAR: SOURCE DATA vs PRE-COMPUTED")
print("="*80)

# Step 1: Load NICAM source data from catalog
print("\n" + "="*80)
print("STEP 1: LOADING NICAM SOURCE DATA FROM CATALOG")
print("="*80)

CATALOG_URL = "https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
cat = intake.open_catalog(CATALOG_URL)["NERSC"]

print("Loading NICAM gl11 with zoom=8, time=PT6H...")
sys.stdout.flush()

ds_source = cat["nicam_gl11"](zoom=8, time="PT6H").to_dask().pipe(
    egh.attach_coords, signed_lon=True
)
ds_source = ds_source.assign_coords(time=convert_time(ds_source.time.values))

# Apply model fixes (rename 'lev' to 'pressure')
if 'lev' in ds_source.dims:
    ds_source = ds_source.rename({'lev': 'pressure'})
    print("Renamed 'lev' → 'pressure'")

print(f"\nSource dataset loaded:")
print(f"  Variables: {list(ds_source.data_vars)[:20]}...")
print(f"  Dimensions: {dict(ds_source.dims)}")
print(f"  Time steps: {len(ds_source.time)}")
print(f"  Pressure levels: {ds_source.pressure.values if 'pressure' in ds_source.coords else 'N/A'}")

# Check if ua and va exist
if 'ua' not in ds_source.data_vars or 'va' not in ds_source.data_vars:
    print("\n❌ ERROR: ua and va not found in source data!")
    print(f"Available variables: {list(ds_source.data_vars)}")
    sys.exit(1)

print(f"\n✓ Found wind variables: ua, va")
print(f"  ua shape: {ds_source['ua'].shape}")
print(f"  va shape: {ds_source['va'].shape}")

# Step 2: Check NaN percentage at each pressure level
print("\n" + "="*80)
print("STEP 2: CHECKING NaN PERCENTAGE AT EACH PRESSURE LEVEL")
print("="*80)

# Select a sample time (first time step)
print("\nLoading first time step to check pressure levels...")
sys.stdout.flush()

ua_sample = ds_source['ua'].isel(time=0).compute()
va_sample = ds_source['va'].isel(time=0).compute()

print(f"\nNaN analysis for each pressure level (time step 0):")
print("-" * 80)
print(f"{'Pressure (hPa)':<15} {'ua NaN %':<15} {'va NaN %':<15} {'Status'}")
print("-" * 80)

pressure_levels = ds_source.pressure.values

nan_stats = {}
for p in pressure_levels:
    ua_level = ua_sample.sel(pressure=p, method='nearest').values
    va_level = va_sample.sel(pressure=p, method='nearest').values
    
    ua_nan_pct = 100 * np.isnan(ua_level).sum() / ua_level.size
    va_nan_pct = 100 * np.isnan(va_level).sum() / va_level.size
    
    status = "✓" if ua_nan_pct < 10 and va_nan_pct < 10 else "⚠️" if ua_nan_pct < 50 else "❌"
    
    print(f"{p:<15.1f} {ua_nan_pct:<15.2f} {va_nan_pct:<15.2f} {status}")
    
    nan_stats[p] = {
        'ua_nan_pct': ua_nan_pct,
        'va_nan_pct': va_nan_pct
    }

# Step 3: Manually compute wind shear and check NaNs
print("\n" + "="*80)
print("STEP 3: MANUALLY COMPUTING WIND SHEAR")
print("="*80)

print("\nComputing LOW-SHEAR (400 hPa - 1000 hPa)...")
sys.stdout.flush()

# Get the wind components
ua_1000 = ua_sample.sel(pressure=1000, method='nearest')
va_1000 = va_sample.sel(pressure=1000, method='nearest')
ua_400 = ua_sample.sel(pressure=400, method='nearest')
va_400 = va_sample.sel(pressure=400, method='nearest')

print(f"  ua_1000 NaN%: {100*np.isnan(ua_1000.values).sum()/ua_1000.size:.2f}%")
print(f"  va_1000 NaN%: {100*np.isnan(va_1000.values).sum()/va_1000.size:.2f}%")
print(f"  ua_400 NaN%:  {100*np.isnan(ua_400.values).sum()/ua_400.size:.2f}%")
print(f"  va_400 NaN%:  {100*np.isnan(va_400.values).sum()/va_400.size:.2f}%")

# Compute shear
du_low = ua_400 - ua_1000
dv_low = va_400 - va_1000
low_shear_mag = np.sqrt(du_low**2 + dv_low**2)

low_shear_nan_pct = 100 * np.isnan(low_shear_mag.values).sum() / low_shear_mag.size
print(f"  Computed low_shear NaN%: {low_shear_nan_pct:.2f}%")

print("\nComputing DEEP-SHEAR (100 hPa - 850 hPa)...")
sys.stdout.flush()

ua_850 = ua_sample.sel(pressure=850, method='nearest')
va_850 = va_sample.sel(pressure=850, method='nearest')
ua_100 = ua_sample.sel(pressure=100, method='nearest')
va_100 = va_sample.sel(pressure=100, method='nearest')

print(f"  ua_850 NaN%: {100*np.isnan(ua_850.values).sum()/ua_850.size:.2f}%")
print(f"  va_850 NaN%: {100*np.isnan(va_850.values).sum()/va_850.size:.2f}%")
print(f"  ua_100 NaN%: {100*np.isnan(ua_100.values).sum()/ua_100.size:.2f}%")
print(f"  va_100 NaN%: {100*np.isnan(va_100.values).sum()/va_100.size:.2f}%")

du_deep = ua_100 - ua_850
dv_deep = va_100 - va_850
deep_shear_mag = np.sqrt(du_deep**2 + dv_deep**2)

deep_shear_nan_pct = 100 * np.isnan(deep_shear_mag.values).sum() / deep_shear_mag.size
print(f"  Computed deep_shear NaN%: {deep_shear_nan_pct:.2f}%")

# Step 4: Load pre-computed data and compare
print("\n" + "="*80)
print("STEP 4: COMPARING WITH PRE-COMPUTED FILES")
print("="*80)

import glob
PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/NICAM"
PRECOMPUTED_PATTERN = "nicam_gl11_wind_shear_hp8_6H"

files = sorted(glob.glob(f"{PRECOMPUTED_DIR}/{PRECOMPUTED_PATTERN}.*.nc"))
print(f"\nLoading pre-computed files from {PRECOMPUTED_DIR}...")
print(f"Found {len(files)} files")

ds_precomp = xr.open_mfdataset(files, combine='by_coords')
ds_precomp = ds_precomp.pipe(egh.attach_coords, signed_lon=True)
ds_precomp = ds_precomp.assign_coords(time=convert_time(ds_precomp.time.values))

print(f"Pre-computed dataset:")
print(f"  Time steps: {len(ds_precomp.time)}")
print(f"  Variables: {list(ds_precomp.data_vars)}")

# Load first time step from pre-computed
precomp_low = ds_precomp['low_shear_magnitude'].isel(time=0).compute()
precomp_deep = ds_precomp['deep_shear_magnitude'].isel(time=0).compute()

precomp_low_nan_pct = 100 * np.isnan(precomp_low.values).sum() / precomp_low.size
precomp_deep_nan_pct = 100 * np.isnan(precomp_deep.values).sum() / precomp_deep.size

print(f"\nPre-computed NaN percentages (time step 0):")
print(f"  low_shear_magnitude:  {precomp_low_nan_pct:.2f}%")
print(f"  deep_shear_magnitude: {precomp_deep_nan_pct:.2f}%")

# Summary
print("\n" + "="*80)
print("SUMMARY COMPARISON")
print("="*80)

print(f"\n{'Source':<30} {'Low-Shear NaN %':<20} {'Deep-Shear NaN %'}")
print("-" * 70)
print(f"{'Manually computed (this run)':<30} {low_shear_nan_pct:<20.2f} {deep_shear_nan_pct:.2f}")
print(f"{'Pre-computed files':<30} {precomp_low_nan_pct:<20.2f} {precomp_deep_nan_pct:.2f}")

print("\n" + "="*80)
print("DIAGNOSIS")
print("="*80)

if abs(low_shear_nan_pct - precomp_low_nan_pct) > 5:
    print("\n❌ MISMATCH DETECTED in low_shear!")
    print(f"   Manually computed: {low_shear_nan_pct:.2f}%")
    print(f"   Pre-computed:      {precomp_low_nan_pct:.2f}%")
    print(f"   Difference:        {abs(low_shear_nan_pct - precomp_low_nan_pct):.2f}%")
    print("\n   Possible causes:")
    print("   1. Different time periods used in pre-computation")
    print("   2. Different pressure level selection (nearest vs exact)")
    print("   3. Bug in pre-computation script")
    print("   4. Different source data versions")
else:
    print("\n✓ Low-shear NaN percentages match!")

if abs(deep_shear_nan_pct - precomp_deep_nan_pct) > 5:
    print("\n❌ MISMATCH DETECTED in deep_shear!")
    print(f"   Manually computed: {deep_shear_nan_pct:.2f}%")
    print(f"   Pre-computed:      {precomp_deep_nan_pct:.2f}%")
    print(f"   Difference:        {abs(deep_shear_nan_pct - precomp_deep_nan_pct):.2f}%")
else:
    print("\n✓ Deep-shear NaN percentages match!")

print("\n" + "="*80)
