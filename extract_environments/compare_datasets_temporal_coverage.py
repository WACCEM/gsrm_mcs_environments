"""
Compare temporal coverage between pre-computed and catalog-loaded data

This script checks if pre-computed wind shear data has the same time coverage
as the resampled IFS catalog data to diagnose why track counts differ.

Author: Laura Paccini
Date: December 2, 2025
"""

import xarray as xr
import pandas as pd
import numpy as np
from easygems import healpix as egh
import intake
import sys
from env_extraction_utils import apply_model_fixes, convert_time

# Configuration
CATALOG_URL = "https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
CATALOG_MODEL = "ifs_tco3999_rcbmf"
CATALOG_PARAMS = {"zoom": 7}
MODEL_TIME_FREQ = "3H"

PRECOMPUTED_DIR = "/pscratch/sd/p/paccini/temp/hackathon/wind_shear/IFS"
PRECOMPUTED_PATTERN = "ifs_tco3999_rcbmf_wind_shear_hp7_3H"
VARIABLE_NAME = "deep_shear_magnitude"

START_DATE = "2020-01-01"
END_DATE = "2021-03-01"

def load_precomputed_data():
    """Load pre-computed wind shear data"""
    print("="*60)
    print("LOADING PRE-COMPUTED DATA")
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
    
    print(f"Loading {len(files_to_load)} pre-computed files...")
    for f in files_to_load:
        print(f"  {f}")
    
    # Open files
    ds = xr.open_mfdataset(files_to_load, combine='by_coords')
    ds = ds.pipe(egh.attach_coords, signed_lon=True)
    ds = ds.assign_coords(time=convert_time(ds.time.values))
    
    # Filter by date range
    ds = ds.sel(time=slice(START_DATE, END_DATE))
    
    print(f"\nPre-computed data loaded:")
    print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
    print(f"  Number of time steps: {len(ds.time)}")
    print(f"  Time frequency: {pd.infer_freq(pd.DatetimeIndex(ds.time.values))}")
    print(f"  Variables: {list(ds.data_vars)}")
    print(f"  Shape: {ds[VARIABLE_NAME].shape}")
    
    return ds


def load_catalog_data():
    """Load and resample catalog data (IFS)"""
    print("\n" + "="*60)
    print("LOADING CATALOG DATA")
    print("="*60)
    
    cat = intake.open_catalog(CATALOG_URL)["online"]
    
    print(f"Loading {CATALOG_MODEL} with params {CATALOG_PARAMS}...")
    ds = cat[CATALOG_MODEL](**CATALOG_PARAMS).to_dask().pipe(
        egh.attach_coords, signed_lon=True
    )
    ds = ds.assign_coords(time=convert_time(ds.time.values))
    
    print(f"\nOriginal catalog data (before resampling):")
    print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
    print(f"  Number of time steps: {len(ds.time)}")
    print(f"  Time frequency: {pd.infer_freq(pd.DatetimeIndex(ds.time.values[:100]))}")
    
    # Apply model-specific fixes
    print("\nApplying model-specific fixes...")
    ds = apply_model_fixes(ds, CATALOG_MODEL)
    
    # Resample to 3H (like in the main script)
    print(f"\nResampling from hourly to {MODEL_TIME_FREQ}...")
    ds = ds.resample(time=MODEL_TIME_FREQ).first()
    
    # Filter by date range
    ds = ds.sel(time=slice(START_DATE, END_DATE))
    
    print(f"\nCatalog data after resampling and filtering:")
    print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
    print(f"  Number of time steps: {len(ds.time)}")
    print(f"  Time frequency: {pd.infer_freq(pd.DatetimeIndex(ds.time.values))}")
    print(f"  Variables: {list(ds.data_vars)[:10]}...")  # Show first 10
    
    return ds


def compare_times(precomputed_ds, catalog_ds):
    """Compare time coordinates between datasets"""
    print("\n" + "="*60)
    print("TIME COMPARISON")
    print("="*60)
    
    precomp_times = pd.DatetimeIndex(precomputed_ds.time.values)
    catalog_times = pd.DatetimeIndex(catalog_ds.time.values)
    
    print(f"\nPre-computed: {len(precomp_times)} time steps")
    print(f"Catalog:      {len(catalog_times)} time steps")
    print(f"Difference:   {len(catalog_times) - len(precomp_times)} time steps")
    
    # Find missing times in pre-computed data
    missing_in_precomp = catalog_times.difference(precomp_times)
    if len(missing_in_precomp) > 0:
        print(f"\n⚠️  {len(missing_in_precomp)} times in CATALOG but NOT in PRE-COMPUTED:")
        print(f"  First 20: {list(missing_in_precomp[:20])}")
        if len(missing_in_precomp) > 20:
            print(f"  ... ({len(missing_in_precomp) - 20} more)")
    
    # Find extra times in pre-computed data
    extra_in_precomp = precomp_times.difference(catalog_times)
    if len(extra_in_precomp) > 0:
        print(f"\n⚠️  {len(extra_in_precomp)} times in PRE-COMPUTED but NOT in CATALOG:")
        print(f"  First 20: {list(extra_in_precomp[:20])}")
        if len(extra_in_precomp) > 20:
            print(f"  ... ({len(extra_in_precomp) - 20} more)")
    
    # Find common times
    common_times = precomp_times.intersection(catalog_times)
    print(f"\n✓ {len(common_times)} times are COMMON to both datasets")
    
    # Check for NaN values in pre-computed data
    print("\n" + "="*60)
    print("DATA QUALITY CHECK")
    print("="*60)
    
    if VARIABLE_NAME in precomputed_ds:
        var_data = precomputed_ds[VARIABLE_NAME]
        total_values = var_data.size
        
        # Check for NaNs
        print(f"\nPre-computed {VARIABLE_NAME}:")
        print(f"  Total values: {total_values:,}")
        
        # Check a sample (computing all would take too long)
        print(f"  Checking first 10 time steps for NaNs...")
        sample_data = var_data.isel(time=slice(0, min(10, len(var_data.time)))).compute()
        nan_count = np.isnan(sample_data).sum().values
        print(f"  NaN count (first 10 times): {nan_count:,}")
        print(f"  NaN percentage: {100 * nan_count / sample_data.size:.2f}%")
        
        # Check time coverage by looking at which times have all-NaN data
        print(f"\n  Checking for time steps with all-NaN data...")
        all_nan_times = []
        for t_idx in range(min(100, len(var_data.time))):  # Check first 100 times
            time_slice = var_data.isel(time=t_idx).compute()
            if np.all(np.isnan(time_slice)):
                all_nan_times.append(var_data.time.values[t_idx])
        
        if all_nan_times:
            print(f"  ⚠️  Found {len(all_nan_times)} time steps with ALL NaN values (checked first 100):")
            print(f"    {all_nan_times[:10]}")
        else:
            print(f"  ✓ No all-NaN time steps found (checked first 100)")


def main():
    """Main comparison function"""
    print("Comparing pre-computed vs catalog data temporal coverage\n")
    
    # Load datasets
    precomputed_ds = load_precomputed_data()
    catalog_ds = load_catalog_data()
    
    # Compare times
    compare_times(precomputed_ds, catalog_ds)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("\nThis comparison shows whether the pre-computed data has:")
    print("1. The same time steps as the resampled catalog data")
    print("2. Any missing or extra time steps")
    print("3. Any data quality issues (NaNs)")
    print("\nIf there are missing times in the pre-computed data, this would")
    print("explain why fewer tracks are processed (tracks with times not in")
    print("pre-computed data would fail extraction).")
    print("="*60)


if __name__ == "__main__":
    main()
