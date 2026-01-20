"""
Check for NaN values in pre-computed wind shear data for all models

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

def check_model_nans(model_name, precomputed_dir, precomputed_pattern, variable_name):
    """Check NaN values for a specific model"""
    
    print("\n" + "="*80)
    print(f"CHECKING {model_name.upper()}")
    print("="*80)
    
    # Find all files matching the pattern in the directory
    import glob
    import os
    
    pattern_glob = f"{precomputed_dir}/{precomputed_pattern}.*.nc"
    files_to_load = sorted(glob.glob(pattern_glob))
    
    if len(files_to_load) == 0:
        print(f"\n❌ ERROR: No files found matching pattern: {pattern_glob}")
        return {'model': model_name, 'error': 'No files found'}
    
    print(f"\nFound {len(files_to_load)} pre-computed files in {precomputed_dir}")
    print(f"Pattern: {precomputed_pattern}.*.nc")
    sys.stdout.flush()
    
    try:
        # Open files
        ds = xr.open_mfdataset(files_to_load, combine='by_coords')
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        ds = ds.assign_coords(time=convert_time(ds.time.values))
        
        print(f"Loaded dataset:")
        print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
        print(f"  Number of time steps: {len(ds.time)}")
        print(f"  Variables: {list(ds.data_vars)}")
        print(f"  Shape: {ds[variable_name].shape}")
        
        var_data = ds[variable_name]
        print(f"\nVariable: {variable_name}")
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
        
        if len(all_nan_times) > 0:
            print(f"\n⚠️  WARNING: {len(all_nan_times)} time steps with ALL NaN values found!")
            print(f"  First 10 all-NaN time steps:")
            for time in all_nan_times[:10]:
                print(f"    {time}")
            if len(all_nan_times) > 10:
                print(f"    ... and {len(all_nan_times) - 10} more")
            
            # Analyze temporal pattern
            if len(all_nan_times) > 1:
                all_nan_df = pd.DataFrame({'time': all_nan_times})
                all_nan_df['date'] = pd.to_datetime(all_nan_df['time']).dt.date
                dates_with_all_nans = all_nan_df['date'].unique()
                print(f"\n  Dates with all-NaN time steps: {len(dates_with_all_nans)}")
                print(f"  First 10 dates: {list(dates_with_all_nans[:10])}")
        else:
            print(f"\n✓ No time steps with all NaN values - data is complete!")
        
        # Check spatial distribution
        nan_per_cell = np.isnan(var_computed.values).sum(axis=0)
        cells_with_nans = (nan_per_cell > 0).sum()
        cells_all_nans = (nan_per_cell == len(var_computed.time)).sum()
        total_cells = var_computed.shape[1]
        
        print(f"\nSpatial NaN Statistics:")
        print(f"  Total cells:                   {total_cells:,}")
        print(f"  Cells with ANY NaNs:           {cells_with_nans:,} ({100*cells_with_nans/total_cells:.2f}%)")
        print(f"  Cells with ALL NaNs:           {cells_all_nans:,} ({100*cells_all_nans/total_cells:.2f}%)")
        print(f"  Cells with NO NaNs:            {(total_cells - cells_with_nans):,} ({100*(total_cells-cells_with_nans)/total_cells:.2f}%)")
        
        return {
            'model': model_name,
            'total_timesteps': len(var_computed.time),
            'timesteps_with_all_nans': len(all_nan_times),
            'total_nan_values': nan_count,
            'total_values': total_count,
            'nan_percentage': 100 * nan_count / total_count,
            'cells_with_all_nans': cells_all_nans
        }
        
    except Exception as e:
        print(f"\n❌ ERROR loading {model_name}: {e}")
        return {
            'model': model_name,
            'error': str(e)
        }


# Model configurations
models = [
    # {
    #     'name': 'IFS',
    #     'dir': '/pscratch/sd/p/paccini/temp/hackathon/wind_shear/IFS',
    #     'pattern': 'ifs_tco3999_rcbmf_wind_shear_hp7_3H',
    #     'variable': 'deep_shear_magnitude'
    # },
    {
        'name': 'NICAM',
        'dir': '/pscratch/sd/p/paccini/temp/hackathon/wind_shear/NICAM',
        'pattern': 'nicam_gl11_wind_shear_hp8_6H',
        'variable': 'low_shear_magnitude'
    },
    {
        'name': 'NICAM',
        'dir': '/pscratch/sd/p/paccini/temp/hackathon/wind_shear/NICAM',
        'pattern': 'nicam_gl11_wind_shear_hp8_6H',
        'variable': 'deep_shear_magnitude'
    }
]

# Check all models
print("="*80)
print("CHECKING PRE-COMPUTED WIND SHEAR DATA FOR ALL MODELS")
print("="*80)

results = []
# Check all models
print("="*80)
print("CHECKING PRE-COMPUTED WIND SHEAR DATA FOR ALL MODELS")
print("="*80)

results = []
for model in models:
    result = check_model_nans(
        model['name'],
        model['dir'],
        model['pattern'],
        model['variable']
    )
    results.append(result)
print(f"\n{'Model':<15} {'Total Times':<15} {'All-NaN Times':<15} {'NaN %':<15} {'Status'}")
print("-" * 80)

for result in results:
    if 'error' in result:
        print(f"{result['model']:<15} {'ERROR':<15} {'-':<15} {'-':<15} ❌")
    else:
        status = "✓" if result['timesteps_with_all_nans'] == 0 else "⚠️"
        print(f"{result['model']:<15} {result['total_timesteps']:<15} "
              f"{result['timesteps_with_all_nans']:<15} "
              f"{result['nan_percentage']:<15.4f} {status}")

print("\n" + "="*80)
print("IMPLICATIONS FOR TRACK EXTRACTION")
print("="*80)
print("\nModels with all-NaN time steps will process fewer tracks because:")
print("  - Tracks occurring during NaN periods cannot extract valid data")
print("  - These tracks are dropped from the final statistics")
print("  - The difference in track counts = tracks in NaN periods")
print("\nRecommendation:")
print("  - Regenerate pre-computed data to fill missing time steps")
print("  - Or use direct catalog loading (slower but complete data)")
print("="*80)
