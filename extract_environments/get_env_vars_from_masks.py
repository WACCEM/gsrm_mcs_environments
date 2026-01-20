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
from easygems import healpix as egh

# Import utility functions
from env_extraction_utils import (
    convert_time, parse_pressure_levels, normalize_pressure_levels,
    convert_w_to_omega, convert_omega_to_w, compute_surface_wind_speed,
    compute_latent_heat_flux, apply_model_fixes, subsample_tracks_by_frequency
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
        Mask data with dimensions (time, cell) - should already contain the exact time
    track_id : int
        Track ID to find in mask
    track_time : timestamp
        Time to extract mask (should already exist in mask_data.time)
    
    Returns:
    --------
    np.ndarray or None
        Array of cell indices, or None if no cells found
    """
    try:
        # Exact selection - times are standardized to pd.Timestamp in the batch
        mask_at_time = mask_data.sel(time=track_time)
        
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
        Variable to extract (dimensions should include 'time' and spatial dimension) - should already contain the exact time
    mask_cells : np.ndarray
        Array of cell indices to extract
    data_time : timestamp
        Time to extract from variable data (should already exist in variable_data.time)
    
    Returns:
    --------
    dict or None
        Dictionary with statistics (mean, median, min, max, std, count, num_valid)
    """
    try:
        # Exact selection - times are standardized to pd.Timestamp in the batch
        var_at_time = variable_data.sel(time=data_time)
        
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


def align_mask_times_to_model_frequency(mask_times, model_freq):
    """
    Filter mask times to align with model output frequency.
    
    This ensures that mask times are sampled at intervals matching the model frequency.
    For example, for 3H model frequency, keep only times at 00:00, 03:00, 06:00, etc.
    
    Parameters:
    -----------
    mask_times : array-like
        Array of mask times (as timestamps)
    model_freq : str
        Model frequency (e.g., '1H', '3H', '6H')
    
    Returns:
    --------
    numpy.ndarray
        Filtered mask times aligned to model frequency
    """
    mask_times_pd = pd.to_datetime(mask_times)
    
    # Parse frequency to hours
    freq_hours = int(model_freq.replace('H', '').replace('h', ''))
    
    # Keep only times where hour is divisible by freq_hours
    mask = mask_times_pd.hour % freq_hours == 0
    aligned_times = mask_times_pd[mask]
    
    print(f"  Aligned mask times from {len(mask_times)} to {len(aligned_times)} (model freq: {model_freq})")
    sys.stdout.flush()
    
    return aligned_times.values


def extract_variable_statistics_from_masks(track_df, mask_data, variable_data, 
                                           batch_size=50, variable_name='var', model_freq='3H'):
    """
    Extract variable statistics for all tracks using small_batch streaming approach.
    
    This approach uses subsample_tracks_by_frequency to filter track times to model frequency,
    then loads masks for small batches of unique times (batch_size at a time), processes all 
    tracks at those times, then moves to the next batch. This amortizes I/O overhead by reusing 
    loaded mask time slices across multiple tracks.
    
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
    model_freq : str
        Model output frequency (e.g., '3H') for subsampling
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with columns: track_id, time_idx, data_time, time_offset_hours,
                                mean, median, min, max, std, count, num_valid
    """
    print(f"\nExtracting {variable_name} statistics using track masks (subsample approach)...")
    sys.stdout.flush()
    
    total_points = len(track_df)
    print(f"  Original track-time combinations: {total_points}")
    
    # Step 1: Subsample tracks to match model frequency
    # Keeps times where (time - track_start) % model_freq == 0
    track_df = subsample_tracks_by_frequency(track_df.copy(), model_freq)
    print(f"  After track subsampling: {len(track_df)} track-time combinations")
    
    # Step 2: Align mask times to model frequency
    # This ensures mask data is also at model frequency intervals
    print(f"\n  Aligning mask times to model frequency...")
    sys.stdout.flush()
    available_mask_times = pd.to_datetime(mask_data.time.values)
    aligned_mask_times = align_mask_times_to_model_frequency(available_mask_times, model_freq)
    
    # Filter mask data to aligned times only
    mask_data_aligned = mask_data.sel(time=aligned_mask_times)
    print(f"  Mask data filtered to {len(aligned_mask_times)} time steps")
    sys.stdout.flush()
    
    # Get track start times for time offset calculation
    track_start_times = track_df.groupby('track_id')['base_time'].first().to_dict()
    
    # Group by unique base_time for batched processing
    unique_times = sorted(track_df['base_time'].unique())
    n_unique_times = len(unique_times)
    
    print(f"\n  Processing {len(track_df)} track-time combinations across {n_unique_times} unique times")
    print(f"  Batch size: {batch_size} times per batch")
    sys.stdout.flush()
    
    results = []
    failed_count = 0
    no_mask_cells_count = 0
    time_not_found_count = 0
    
    # Process in batches of unique times
    for batch_idx in range(0, n_unique_times, batch_size):
        batch_start_time = time.time()
        batch_times = unique_times[batch_idx:batch_idx + batch_size]
        
        batch_num = batch_idx // batch_size + 1
        total_batches = (n_unique_times + batch_size - 1) // batch_size

        if batch_num % 10 == 0:
            print(f"\n  Batch {batch_num}/{total_batches}: Loading {len(batch_times)} time slices...")
        sys.stdout.flush()
        
        # Load mask and variable data for this batch of track times
        # Use method='nearest' to handle any minor time mismatches between tracks and aligned masks
        try:
            mask_batch = mask_data_aligned.sel(time=batch_times, method='nearest').compute()
            variable_batch = variable_data.sel(time=batch_times, method='nearest').compute()
        except Exception as e:
            print(f"  ERROR loading data for batch: {e}")
            sys.stdout.flush()
            continue
        
        # Standardize time coordinates to pandas Timestamps for consistent selection
        mask_batch['time'] = pd.to_datetime(mask_batch.time.values)
        variable_batch['time'] = pd.to_datetime(variable_batch.time.values)
        
        # Create time mapping: track_time -> actual_mask_time/model_time (as selected)
        # The 'method=nearest' above may have selected different times than requested
        actual_mask_times = mask_batch.time.values
        actual_var_times = variable_batch.time.values
        
        time_mapping = {}
        for i, requested_time in enumerate(batch_times):
            if i < len(actual_mask_times) and i < len(actual_var_times):
                # Ensure mask and variable times match
                mask_time = pd.Timestamp(actual_mask_times[i])
                var_time = pd.Timestamp(actual_var_times[i])
                
                # Use the mask time as reference (should be same as var_time)
                time_mapping[requested_time] = mask_time
        
        # Get all tracks at these base times
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
            
            # Map to the actual time that was selected
            if track_time not in time_mapping:
                time_not_found_count += 1
                continue
            
            actual_time = time_mapping[track_time]
            
            try:
                # Get mask cells for this track-time (from batched mask)
                # Use actual_time for exact selection (already loaded with nearest)
                # Masks start at 1, track_ids (from stats file) start at 0
                mask_cells = get_mask_cells_for_track(mask_batch, track_id + 1, actual_time)

                if mask_cells is None or len(mask_cells) == 0:
                    no_mask_cells_count += 1
                    continue
                
                # Extract statistics (from batched variable data)
                # Use actual_time for exact selection (already loaded with nearest)
                stats = extract_statistics_from_mask(variable_batch, mask_cells, actual_time)
                
                if stats is None:
                    failed_count += 1
                    continue
                
                # Calculate time offset from track start
                time_offset_hours = (track_time - track_start_times[track_id]).total_seconds() / 3600
                
                # Store result (use actual_time as data_time to show actual extraction time)
                result = {
                    'track_id': track_id,
                    'time_idx': time_idx,
                    'data_time': actual_time,
                    'time_offset_hours': time_offset_hours,
                    **stats
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"    WARNING: Error processing track {track_id} at time_idx {time_idx}: {e}")
                sys.stdout.flush()
                failed_count += 1
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
    
    # Print diagnostic summary
    print(f"\n  ============ EXTRACTION SUMMARY ============")
    print(f"  Input track-time combinations: {len(track_df)}")
    print(f"  Successful extractions: {len(result_df)}")
    print(f"  Failed extractions breakdown:")
    print(f"    - Time not found in mapping: {time_not_found_count}")
    print(f"    - No mask cells found: {no_mask_cells_count}")
    print(f"    - Statistics extraction failed: {failed_count}")
    print(f"  Success rate: {100*len(result_df)/len(track_df):.1f}%" if len(track_df) > 0 else "  Success rate: N/A")
    print(f"  Unique tracks processed: {result_df['track_id'].nunique() if len(result_df) > 0 else 0}")
    print(f"  ============================================")
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
    
    # Input/output options - either zarr or catalog (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--zarr_path',
                            help='Path to zarr file (for direct zarr loading, e.g., ERA5)')
    input_group.add_argument('--catalog_url',
                            help='URL of the intake catalog (for catalog-based loading)')
    
    parser.add_argument('--zarr_model_name',
                        help='Model name when using zarr_path (e.g., "era5")')
    parser.add_argument('--current_location', default="NERSC",
                        help='Current location in catalog (catalog mode only)')
    parser.add_argument('--catalog_model',
                        help='Model name in the catalog (catalog mode only)')
    parser.add_argument('--catalog_params',
                        help='Catalog parameters as string (e.g., \'{"zoom": 8, "time": "PT3H"}\') (catalog mode only)')
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
    
    # Validate arguments
    if args.zarr_path and not args.zarr_model_name:
        parser.error("--zarr_model_name is required when using --zarr_path")
    if args.catalog_url and (not args.catalog_model or not args.catalog_params):
        parser.error("--catalog_model and --catalog_params are required when using --catalog_url")
    
    # Determine model name for output and fixes
    model_name = args.zarr_model_name if args.zarr_path else args.catalog_model
    
    print("="*60)
    print("MASK-BASED ENVIRONMENTAL VARIABLE EXTRACTION")
    print("="*60)
    if args.zarr_path:
        print(f"Data source: Direct zarr file")
        print(f"Zarr path: {args.zarr_path}")
        print(f"Model: {model_name}")
    else:
        print(f"Data source: Intake catalog")
        print(f"Catalog: {args.catalog_url}")
        print(f"Model: {model_name}")
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

    
    # Convert base_time to datetime
    df_tracks['base_time'] = pd.to_datetime(df_tracks['base_time'])
    
    print(f"Loaded {len(df_tracks)} track time points")
    # print(f"Unique tracks: {df_tracks['track_id'].nunique()}")
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
    # print(f"Unique tracks: {df_spatial_filtered['track_id'].nunique()}")
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
    # LOAD MODEL DATA (ZARR OR CATALOG)
    # =================================================================
    print("\n" + "="*60)
    if args.zarr_path:
        print("LOADING MODEL DATA FROM ZARR FILE")
        print("="*60)
        sys.stdout.flush()
        
        print(f"Opening zarr file: {args.zarr_path}")
        sys.stdout.flush()
        
        # Open zarr with chunking
        ds = xr.open_zarr(args.zarr_path, chunks={'time': 1, 'cell': -1})
        
        # Attach HEALPix coordinates
        print("Attaching HEALPix coordinates...")
        sys.stdout.flush()
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        
        # Apply model-specific fixes
        model_name = args.zarr_model_name
        ds = apply_model_fixes(ds, model_name)
        
        # Convert time coordinate
        print("Converting time coordinate...")
        sys.stdout.flush()
        ds = ds.assign_coords(time=convert_time(ds.time.values))
        
        print(f"Dataset loaded: {list(ds.data_vars)}")
        print(f"Dataset dimensions: {list(ds.dims)}")
        print(f"Dataset time range: {ds.time.values[0]} to {ds.time.values[-1]}")
        sys.stdout.flush()
    else:
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
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        model_name = args.catalog_model
        ds = apply_model_fixes(ds, model_name)
        
        # Convert time coordinate
        ds = ds.assign_coords(time=convert_time(ds.time.values))
        
        print(f"Dataset loaded: {list(ds.data_vars)}")
        print(f"Dataset dimensions: {list(ds.dims)}")
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
        
        # Special case: hflssd computation (may use 'ie' for ERA5)
        elif variable_name.lower() == 'hflssd':
            print("Loading or computing surface latent heat flux (hflssd)...")
            sys.stdout.flush()
            
            try:
                variable_data = compute_latent_heat_flux(ds)
                print("hflssd ready")
            except Exception as e:
                print(f"ERROR: Failed to get/compute hflssd: {e}")
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
            
            # NOTE: Subsampling is now handled inside extract_variable_statistics_from_masks
            # via align_track_times_to_model_frequency, so we don't need to subsample here
            
            # Rename columns for consistency
            column_rename_map = {}
            if 'tracks' in filtered_df.columns:
                column_rename_map['tracks'] = 'track_id'
            if 'times' in filtered_df.columns:
                column_rename_map['times'] = 'time_idx'
            
            if column_rename_map:
                filtered_df = filtered_df.rename(columns=column_rename_map)
            
            # Check for duplicates
            duplicates = filtered_df[filtered_df.duplicated(subset=['track_id', 'base_time'], keep=False)]
            if len(duplicates) > 0:
                print(f"  WARNING: Found {len(duplicates)} duplicate (track_id, base_time) combinations!")
                print(f"  Example duplicates:\n{duplicates.head()}")
                # Remove duplicates, keeping first occurrence
                filtered_df = filtered_df.drop_duplicates(subset=['track_id', 'base_time'], keep='first')
                print(f"  After deduplication: {len(filtered_df)} track-time combinations")
            
            if len(filtered_df) == 0:
                print(f"WARNING: No tracks remain after processing, skipping")
                continue

            

            # # Ensure required columns exist
            # if 'track_id' not in filtered_df.columns or 'time_idx' not in filtered_df.columns:
            #     raise ValueError("Track file must have 'tracks' and 'times' dimensions")
            
            # # Ensure base_time exists
            # if 'base_time' not in filtered_df.columns:
            #     raise ValueError("Track file must have 'base_time' coordinate")
    
            # Extract statistics using masks
            stats_df = extract_variable_statistics_from_masks(
                filtered_df,
                mask_data,
                variable_data,
                batch_size=args.batch_size,
                variable_name=variable_name,
                model_freq=args.model_time_freq
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
