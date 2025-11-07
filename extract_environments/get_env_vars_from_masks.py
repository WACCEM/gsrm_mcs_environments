"""
Extract environmental variables using MCS track masks

This script extracts environmental variables (temperature, humidity, etc.) from model output
using MCS track masks instead of circular areas. For each track at each time step, it:
1. Loads the mask file to find all cells belonging to that track
2. Extracts statistics (mean, median, min, max, std) for those cells

Key differences from circular area extraction:
- Uses actual MCS masks (mcs_mask variable with track IDs)
- No pre-convective period (only track duration)
- No radius parameter (mask defines the area)
- Handles hourly masks vs 3H/6H model output

Author: Laura Paccini
Last updated: November 2025
"""

import numpy as np
import pandas as pd
import xarray as xr
import argparse
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
import intake

# Import utility functions
from env_extraction_utils import (
    convert_time, parse_pressure_levels, normalize_pressure_levels,
    convert_w_to_omega, convert_omega_to_w, compute_surface_wind_speed,
    apply_model_fixes, subsample_tracks_by_frequency
)

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)


def load_mask_file(mask_path, verbose=False):
    """
    Load mask file with explicit chunking for memory-efficient access.
    
    Parameters:
    -----------
    mask_path : str
        Path to the mask zarr file
    verbose : bool
        Whether to print debugging information
        
    Returns:
    --------
    xr.DataArray
        The mask DataArray with optimized chunking
    """
    if verbose:
        print(f"\nOpening mask file: {mask_path}")
        sys.stdout.flush()
    
    # Open with explicit chunking: 1 time × all cells per chunk
    ds_mask = xr.open_zarr(mask_path, chunks={'time': 1, 'cell': -1})
    
    # Assume the main variable is 'mcs_mask' or the first data variable
    if 'mcs_mask' in ds_mask:
        mask = ds_mask['mcs_mask']
    else:
        mask = ds_mask[list(ds_mask.data_vars)[0]]
    
    if verbose:
        print(f"Mask shape: {mask.shape}")
        print(f"Mask chunks: {mask.chunks}")
        sys.stdout.flush()
    
    return mask


def get_mask_cells_for_track(mask_data, track_id, track_time):
    """
    Get all cell indices where mask equals track_id at given time.
    
    Parameters:
    -----------
    mask_data : xarray.DataArray
        Mask data with dimensions (time, cell)
    track_id : int
        Track ID to find in mask
    track_time : pd.Timestamp
        Time to extract mask
    
    Returns:
    --------
    np.ndarray or None
        Array of cell indices, or None if no cells found
    """
    try:
        # Select nearest time
        mask_at_time = mask_data.sel(time=track_time, method='nearest')
        
        # Find cells where mask == track_id
        cells = np.where(mask_at_time.values == track_id)[0]
        
        if len(cells) == 0:
            return None
        
        return cells
    
    except Exception as e:
        print(f"    WARNING: Error getting mask for track {track_id} at {track_time}: {e}")
        return None


def extract_statistics_from_mask(variable_data, mask_cells, data_time):
    """
    Extract statistics from variable data for given mask cells.
    
    Parameters:
    -----------
    variable_data : xarray.DataArray
        Variable to extract (dimensions should include 'time' and spatial dimension)
    mask_cells : np.ndarray
        Array of cell indices to extract
    data_time : pd.Timestamp
        Time to extract from variable data
    
    Returns:
    --------
    dict or None
        Dictionary with statistics (mean, median, min, max, std, count, num_valid)
    """
    try:
        # Select nearest time in variable data
        var_at_time = variable_data.sel(time=data_time, method='nearest')
        
        # Determine spatial dimension name (ncells, cell, value, etc.)
        spatial_dims = [d for d in var_at_time.dims if d != 'time']
        if len(spatial_dims) == 0:
            print(f"    WARNING: No spatial dimension found in variable data")
            return None
        
        spatial_dim = spatial_dims[0]
        
        # Extract values for mask cells
        if spatial_dim in var_at_time.dims:
            values = var_at_time.isel({spatial_dim: mask_cells}).values
        else:
            print(f"    WARNING: Spatial dimension '{spatial_dim}' not found")
            return None
        
        # Remove NaN values
        valid_values = values[~np.isnan(values)]
        
        if len(valid_values) == 0:
            return None
        
        # Calculate statistics
        stats = {
            'mean': float(np.mean(valid_values)),
            'median': float(np.median(valid_values)),
            'min': float(np.min(valid_values)),
            'max': float(np.max(valid_values)),
            'std': float(np.std(valid_values)),
            'count': len(values),
            'num_valid': len(valid_values)
        }
        
        return stats
    
    except Exception as e:
        print(f"    WARNING: Error extracting statistics: {e}")
        return None


def extract_variable_statistics_from_masks(track_df, mask_data, variable_data, 
                                           batch_size=50, variable_name='var'):
    """
    Extract variable statistics for all tracks using small_batch streaming approach.
    
    This approach loads masks for small batches of unique times (batch_size at a time),
    processes all tracks at those times, then moves to the next batch. This amortizes
    I/O overhead by reusing loaded mask time slices across multiple tracks.
    
    Parameters:
    -----------
    track_df : pd.DataFrame
        DataFrame with columns: track_id, time_idx, base_time
    mask_data : xarray.DataArray
        Mask data with track IDs (dimensions: time, cell)
    variable_data : xarray.DataArray
        Variable to extract (dimensions: time, spatial_dim)
    batch_size : int
        Number of unique times to load at once (default: 50)
    variable_name : str
        Name of variable (for progress messages)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with columns: track_id, time_idx, data_time, time_offset_hours,
                                mean, median, min, max, std, count, num_valid
    """
    print(f"\nExtracting {variable_name} statistics using track masks (small_batch approach)...")
    sys.stdout.flush()
    
    total_points = len(track_df)
    print(f"  Processing {total_points} track-time combinations")
    
    # Get track start times for time offset calculation
    track_start_times = track_df.groupby('track_id')['base_time'].first().to_dict()
    
    # Group by unique times for batched processing
    unique_times = sorted(track_df['base_time'].unique())
    n_unique_times = len(unique_times)
    
    print(f"  Unique times: {n_unique_times}")
    print(f"  Batch size: {batch_size} times per batch")
    sys.stdout.flush()
    
    results = []
    
    # Process in batches of unique times
    for batch_idx in range(0, n_unique_times, batch_size):
        batch_start_time = time.time()
        batch_times = unique_times[batch_idx:batch_idx + batch_size]
        
        batch_num = batch_idx // batch_size + 1
        total_batches = (n_unique_times + batch_size - 1) // batch_size

        if batch_num % 10 == 0:
            print(f"\n  Batch {batch_num}/{total_batches}: Loading {len(batch_times)} time slices...")
        sys.stdout.flush()
        
        # Load mask data for this batch of times (memory-efficient with .sel)
        mask_batch = mask_data.sel(time=batch_times, method='nearest')
        variable_batch = variable_data.sel(time=batch_times, method='nearest')
        
        # Load into memory to avoid repeated lazy selections
        # print(f"  Loading data into memory...")
        sys.stdout.flush()
        mask_batch = mask_batch.compute()
        variable_batch = variable_batch.compute()
        
        # Get all tracks at these times
        df_batch = track_df[track_df['base_time'].isin(batch_times)]
        n_batch_tracks = len(df_batch)
        
        if batch_num % 10 == 0:
            print(f"  Processing {n_batch_tracks} track-time combinations in this batch...")
            sys.stdout.flush()
        
        # Process each track-time in the batch
        for idx, row in df_batch.iterrows():
            track_id = int(row['track_id'])
            time_idx = int(row['time_idx'])
            track_time = pd.Timestamp(row['base_time'])
            
            try:
                # Get mask cells for this track-time (from batched mask)
                # Masks start at 1, track_ids (from stats file) start at 0
                mask_cells = get_mask_cells_for_track(mask_batch, track_id + 1, track_time)

                if mask_cells is None or len(mask_cells) == 0:
                    continue
                
                # Extract statistics (from batched variable data)
                stats = extract_statistics_from_mask(variable_batch, mask_cells, track_time)
                
                if stats is None:
                    continue
                
                # Calculate time offset from track start
                time_offset_hours = (track_time - track_start_times[track_id]).total_seconds() / 3600
                
                # Store result
                result = {
                    'track_id': track_id,
                    'time_idx': time_idx,
                    'data_time': track_time,
                    'time_offset_hours': time_offset_hours,
                    **stats
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"    WARNING: Error processing track {track_id} at offset {time_idx}: {e}")
                sys.stdout.flush()
                continue
        
        batch_elapsed = time.time() - batch_start_time
        ms_per_track = (batch_elapsed / n_batch_tracks * 1000) if n_batch_tracks > 0 else 0
        if batch_num % 10 == 0:
            print(f"  Batch {batch_num} completed in {batch_elapsed:.2f}s ({ms_per_track:.2f} ms per track-time)")
        sys.stdout.flush()
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        result_df = result_df.sort_values(['track_id', 'time_idx']).reset_index(drop=True)
    
    print(f"\n  Extracted statistics for {len(result_df)} track-time combinations")
    print(f"  Unique tracks: {result_df['track_id'].nunique() if len(result_df) > 0 else 0}")
    sys.stdout.flush()
    
    return result_df


def save_results(result_df, output_path, variable_name, pressure_suffix=''):
    """
    Save results to parquet file.
    
    Parameters:
    -----------
    result_df : pd.DataFrame
        Results to save
    output_path : str
        Output path (without extension)
    variable_name : str
        Variable name
    pressure_suffix : str
        Suffix for pressure level info (e.g., '_850hPa')
    
    Returns:
    --------
    str
        Full path to saved file
    """
    output_file = f"{output_path}{pressure_suffix}.parquet"
    
    print(f"\nSaving results to: {output_file}")
    sys.stdout.flush()
    
    result_df.to_parquet(output_file, index=False)
    
    print(f"  Saved {len(result_df)} rows")
    sys.stdout.flush()
    
    return output_file


def main():
    total_start_time = time.time()
    
    parser = argparse.ArgumentParser(
        description='Extract environmental variables using MCS track masks.'
    )
    
    # Input/output options
    parser.add_argument('--catalog_url', required=True,
                        help='URL of the intake catalog')
    parser.add_argument('--current_location', default="NERSC",
                        help='Current location in catalog')
    parser.add_argument('--catalog_model', required=True,
                        help='Model name in the catalog')
    parser.add_argument('--catalog_params', required=True,
                        help='Catalog parameters as string (e.g., \'{"zoom": 8, "time": "PT3H"}\')')
    parser.add_argument('--trackfile', required=True,
                        help='Path to MCS track statistics file (netCDF)')
    parser.add_argument('--mask_file', required=True,
                        help='Path to MCS mask file (zarr format)')
    parser.add_argument('--output_dir', required=True,
                        help='Output directory for results')
    
    # Variable and date range options
    parser.add_argument('--variables', nargs='+', required=True,
                        help='Variable names to extract (e.g., tas huss prw)')
    parser.add_argument('--date_ranges', nargs='+',
                        help='Date ranges as pairs: start1 end1 start2 end2 ...')
    
    # Spatial bounds (for track filtering)
    parser.add_argument('--min_lat', type=float, default=-90,
                        help='Minimum latitude for track filtering')
    parser.add_argument('--max_lat', type=float, default=90,
                        help='Maximum latitude for track filtering')
    parser.add_argument('--min_lon', type=float, default=-180,
                        help='Minimum longitude for track filtering')
    parser.add_argument('--max_lon', type=float, default=180,
                        help='Maximum longitude for track filtering')
    
    # Track file variable names
    parser.add_argument('--lat_var', default='meanlat',
                        help='Latitude variable name in track file')
    parser.add_argument('--lon_var', default='meanlon',
                        help='Longitude variable name in track file')
    
    # Processing options
    parser.add_argument('--batch_size', type=int, default=50,
                        help='Batch size for mask loading (number of unique times to load at once)')
    parser.add_argument('--model_time_freq', default='3H',
                        help='Model output time frequency (e.g., 1H, 3H, 6H)')
    
    # 3D variable options
    parser.add_argument('--pressure_levels', type=str, default=None,
                        help='Pressure levels in hPa (comma-separated, e.g., "850,500,300")')
    parser.add_argument('--convert_wa_to_omega', action='store_true',
                        help='Convert vertical velocity (wa) to pressure velocity (omega)')
    parser.add_argument('--convert_omega_to_wa', action='store_true',
                        help='Convert pressure velocity (omega) to vertical velocity (wa)')
    
    args = parser.parse_args()
    
    print("="*60)
    print("MASK-BASED ENVIRONMENTAL VARIABLE EXTRACTION")
    print("="*60)
    print(f"Model: {args.catalog_model}")
    print(f"Track file: {args.trackfile}")
    print(f"Mask file: {args.mask_file}")
    print(f"Variables: {args.variables}")
    print(f"Model frequency: {args.model_time_freq}")
    print("="*60)
    sys.stdout.flush()
    
    # Parse date ranges
    if args.date_ranges:
        if len(args.date_ranges) % 2 != 0:
            raise ValueError("--date_ranges must have even number of arguments (start end pairs)")
        date_ranges = [(args.date_ranges[i], args.date_ranges[i+1]) 
                       for i in range(0, len(args.date_ranges), 2)]
    else:
        date_ranges = [(None, None)]
    
    print(f"Processing {len(date_ranges)} date range(s)")
    
    # =================================================================
    # LOAD TRACK FILE (ONLY ESSENTIAL VARIABLES!)
    # =================================================================
    print("\n" + "="*60)
    print("LOADING TRACK DATA")
    print("="*60)
    sys.stdout.flush()
    
    ds_tracks = xr.open_dataset(args.trackfile)
    
    # ONLY load essential variables - critical for memory efficiency
    required_vars = [args.lat_var, args.lon_var, 'base_time']
    print(f"Loading only essential variables: {required_vars}")
    subset = ds_tracks[required_vars].compute()
    df_tracks = subset.to_dataframe().reset_index()
    
    # Rename columns for consistency
    column_rename_map = {}
    if 'tracks' in df_tracks.columns:
        column_rename_map['tracks'] = 'track_id'
    if 'times' in df_tracks.columns:
        column_rename_map['times'] = 'time_idx'
    
    if column_rename_map:
        df_tracks = df_tracks.rename(columns=column_rename_map)
    
    # Ensure required columns exist
    if 'track_id' not in df_tracks.columns or 'time_idx' not in df_tracks.columns:
        raise ValueError("Track file must have 'tracks' and 'times' dimensions")
    
    # Ensure base_time exists
    if 'base_time' not in df_tracks.columns:
        raise ValueError("Track file must have 'base_time' coordinate")
    
    # Convert base_time to datetime
    df_tracks['base_time'] = pd.to_datetime(df_tracks['base_time'])
    
    print(f"Loaded {len(df_tracks)} track time points")
    print(f"Unique tracks: {df_tracks['track_id'].nunique()}")
    print(f"Time range: {df_tracks['base_time'].min()} to {df_tracks['base_time'].max()}")
    sys.stdout.flush()
    
    # =================================================================
    # SPATIAL FILTERING
    # =================================================================
    print("\n" + "="*60)
    print("SPATIAL FILTERING")
    print("="*60)
    print(f"Latitude range: [{args.min_lat}, {args.max_lat}]")
    print(f"Longitude range: [{args.min_lon}, {args.max_lon}]")
    sys.stdout.flush()
    
    spatial_filter = (
        (df_tracks[args.lat_var] >= args.min_lat) &
        (df_tracks[args.lat_var] <= args.max_lat) &
        (df_tracks[args.lon_var] >= args.min_lon) &
        (df_tracks[args.lon_var] <= args.max_lon)
    )
    
    df_spatial_filtered = df_tracks[spatial_filter].copy()
    
    print(f"After spatial filtering: {len(df_spatial_filtered)} track time points")
    print(f"Unique tracks: {df_spatial_filtered['track_id'].nunique()}")
    sys.stdout.flush()
    
    if len(df_spatial_filtered) == 0:
        print("ERROR: No tracks remaining after spatial filtering")
        return
    
    # =================================================================
    # LOAD MASK FILE
    # =================================================================
    print("\n" + "="*60)
    print("LOADING MASK FILE")
    print("="*60)
    sys.stdout.flush()
    
    mask_data = load_mask_file(args.mask_file, verbose=False)
    
    # =================================================================
    # LOAD MODEL DATA FROM CATALOG
    # =================================================================
    print("\n" + "="*60)
    print("LOADING MODEL DATA FROM CATALOG")
    print("="*60)
    sys.stdout.flush()
    
    # Parse catalog params
    import ast
    catalog_params = ast.literal_eval(args.catalog_params)
    
    print(f"Opening catalog: {args.catalog_url}")
    print(f"Location: {args.current_location}")
    print(f"Model: {args.catalog_model}")
    print(f"Parameters: {catalog_params}")
    sys.stdout.flush()
    
    # Open catalog at the specified location first, then access model
    cat = intake.open_catalog(args.catalog_url)[args.current_location]
    
    ds = cat[args.catalog_model](**catalog_params).to_dask()
    
    # Apply model-specific fixes
    ds = apply_model_fixes(ds, args.catalog_model)
    
    # Convert time coordinate
    ds = ds.assign_coords(time=convert_time(ds.time.values))
    
    print(f"Dataset loaded: {list(ds.data_vars)}")
    print(f"Dataset time range: {ds.time.values[0]} to {ds.time.values[-1]}")
    sys.stdout.flush()
    
    # Parse pressure levels if provided
    pressure_levels = None
    if args.pressure_levels:
        pressure_levels = parse_pressure_levels(args.pressure_levels)
        print(f"Pressure levels: {pressure_levels} hPa")
    
    # =================================================================
    # PROCESS EACH VARIABLE
    # =================================================================
    for var_idx, variable_name in enumerate(args.variables):
        var_start_time = time.time()
        
        print("\n" + "="*60)
        print(f"Processing variable {var_idx + 1}/{len(args.variables)}: {variable_name}")
        print("="*60)
        sys.stdout.flush()
        
        # Store original variable name
        original_variable = variable_name
        
        # Track pressure level info for output filename
        pressure_suffix = ''
        is_3d_variable = False
        
        # =================================================================
        # HANDLE DIFFERENT VARIABLE TYPES
        # =================================================================
        
        # Special case: sfcWind computation
        if variable_name.lower() == 'sfcwind':
            print("Computing sfcWind from uas and vas...")
            sys.stdout.flush()
            
            try:
                variable_data = compute_surface_wind_speed(ds)
                print("sfcWind computed successfully")
            except Exception as e:
                print(f"ERROR: Failed to compute sfcWind: {e}")
                continue
        
        # Special case: wa -> omega conversion
        elif variable_name == 'wa' and args.convert_wa_to_omega:
            print("Converting wa to omega...")
            sys.stdout.flush()
            
            if pressure_levels is None:
                print("ERROR: --pressure_levels required for wa to omega conversion")
                continue
            
            if 'wa' not in ds or 'ta' not in ds:
                print("ERROR: Variables 'wa' and 'ta' required for omega conversion")
                continue
            
            variable_data = convert_w_to_omega(ds, pressure_levels)
            variable_name = 'omega'
            is_3d_variable = True
            
            if len(pressure_levels) == 1:
                pressure_suffix = f"_{int(pressure_levels[0])}hPa"
            else:
                levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                pressure_suffix = f"_avg{levels_str}hPa"
        
        # Special case: omega -> wa conversion
        elif variable_name == 'omega' and args.convert_omega_to_wa:
            print("Converting omega to wa...")
            sys.stdout.flush()
            
            if pressure_levels is None:
                print("ERROR: --pressure_levels required for omega to wa conversion")
                continue
            
            if 'omega' not in ds or 'ta' not in ds:
                print("ERROR: Variables 'omega' and 'ta' required for wa conversion")
                continue
            
            variable_data = convert_omega_to_w(ds, pressure_levels)
            variable_name = 'wa'
            is_3d_variable = True
            
            if len(pressure_levels) == 1:
                pressure_suffix = f"_{int(pressure_levels[0])}hPa"
            else:
                levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                pressure_suffix = f"_avg{levels_str}hPa"
        
        # Standard variable from catalog
        else:
            print(f"Loading variable: {variable_name}")
            sys.stdout.flush()
            
            try:
                variable_data = ds[variable_name]
                
                # Check if it's a 3D variable with pressure levels
                if 'pressure' in variable_data.dims and pressure_levels is not None:
                    is_3d_variable = True
                    print(f"3D variable detected with pressure dimension")
                    print(f"Requested pressure levels: {pressure_levels} hPa")
                    
                    # Normalize and select pressure levels
                    pressure_levels_dataset, pressure_units = normalize_pressure_levels(
                        pressure_levels, variable_data.pressure
                    )
                    
                    variable_data = variable_data.sel(
                        pressure=pressure_levels_dataset, method='nearest'
                    ).mean(dim='pressure')
                    
                    if len(pressure_levels) == 1:
                        pressure_suffix = f"_{int(pressure_levels[0])}hPa"
                    else:
                        levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                        pressure_suffix = f"_avg{levels_str}hPa"
                
                print(f"Variable data ready")
                
            except KeyError:
                print(f"ERROR: Variable '{variable_name}' not found in dataset")
                continue
        
        # =================================================================
        # PROCESS EACH DATE RANGE FOR THIS VARIABLE
        # =================================================================
        for range_idx, (start_date_str, end_date_str) in enumerate(date_ranges):
            range_start_time = time.time()
            
            print(f"\n" + "="*60)
            print(f"Processing date range {range_idx + 1}/{len(date_ranges)}")
            print(f"Date range: {start_date_str or 'start'} to {end_date_str or 'end'}")
            print("="*60)
            sys.stdout.flush()
            
            # Filter by date range
            if start_date_str and end_date_str:
                start_date = pd.Timestamp(start_date_str)
                end_date = pd.Timestamp(end_date_str)
                date_filter = (
                    (df_spatial_filtered['base_time'] >= start_date) &
                    (df_spatial_filtered['base_time'] <= end_date)
                )
                filtered_df = df_spatial_filtered[date_filter].copy()
                print(f"Filtered to {len(filtered_df)} track time points for this date range")
            else:
                filtered_df = df_spatial_filtered.copy()
                print(f"Processing all {len(filtered_df)} track time points (no date filter)")
            
            if len(filtered_df) == 0:
                print(f"WARNING: No tracks in date range {start_date_str} to {end_date_str}, skipping")
                continue
            
            # Subsample tracks to model frequency if needed
            if args.model_time_freq and args.model_time_freq not in ['1H', '1h']:
                filtered_df = subsample_tracks_by_frequency(filtered_df, args.model_time_freq)
                if len(filtered_df) == 0:
                    print(f"WARNING: No tracks remain after subsampling, skipping")
                    continue
            
            # Extract statistics using masks
            stats_df = extract_variable_statistics_from_masks(
                filtered_df,
                mask_data,
                variable_data,
                batch_size=args.batch_size,
                variable_name=variable_name
            )
            
            if len(stats_df) == 0:
                print(f"WARNING: No data extracted for date range {start_date_str} to {end_date_str}")
                continue
            
            # Save results
            var_output_dir = os.path.join(args.output_dir, variable_name)
            os.makedirs(var_output_dir, exist_ok=True)
            
            start_str = start_date_str.replace('-', '') if start_date_str else "unknown"
            end_str = end_date_str.replace('-', '') if end_date_str else "unknown"
            output_path = os.path.join(
                var_output_dir,
                f"mcs_env_mask_{variable_name}_{start_str}_{end_str}"
            )
            
            output_file = save_results(stats_df, output_path, variable_name, pressure_suffix)
            
            # Print summary
            print("\n" + "="*60)
            print(f"SUMMARY - {variable_name} - Date range {range_idx + 1}/{len(date_ranges)}")
            print("="*60)
            print(f"Total tracks processed: {stats_df['track_id'].nunique()}")
            print(f"Total data points: {len(stats_df)}")
            print(f"Variable: {variable_name}")
            
            if 'time_offset_hours' in stats_df.columns:
                min_offset = stats_df['time_offset_hours'].min()
                max_offset = stats_df['time_offset_hours'].max()
                print(f"Time range: {min_offset:.1f}h to {max_offset:.1f}h")
            
            range_elapsed_time = time.time() - range_start_time
            print(f"\nExtraction completed in {range_elapsed_time:.2f} seconds ({range_elapsed_time/60:.2f} minutes)")
            print("="*60)
        
        # Print summary for this variable
        var_elapsed_time = time.time() - var_start_time
        print("\n" + "="*60)
        print(f"VARIABLE {variable_name} COMPLETED")
        print("="*60)
        print(f"Processed {len(date_ranges)} date range(s)")
        print(f"Total time for {variable_name}: {var_elapsed_time:.2f} seconds ({var_elapsed_time/60:.2f} minutes)")
        print("="*60)
    
    # Print final summary
    total_elapsed_time = time.time() - total_start_time
    print("\n" + "="*60)
    print("ALL VARIABLES AND DATE RANGES COMPLETED")
    print("="*60)
    print(f"Processed {len(args.variables)} variable(s)")
    print(f"Processed {len(date_ranges)} date range(s) per variable")
    print(f"Total time: {total_elapsed_time:.2f} seconds ({total_elapsed_time/60:.2f} minutes)")
    if len(args.variables) > 0:
        print(f"Average time per variable: {total_elapsed_time/len(args.variables):.2f} seconds")
    print("="*60)


if __name__ == "__main__":
    main()
