"""
Extract environmental variable statistics from ERA5 MCS tracking data

This script processes ERA5 environmental variables that are already extracted in 25x25 boxes
centered on MCS track positions. It calculates statistics over circular areas similar to
the get_env_vars.py script for model output.

Input data structure:
- Dimensions: tracks (track ID), rel_times (time offset in hours), y, x (spatial dimensions)
- Spatial grid: 0.25° resolution, centered at (0,0), ranging from -12 to +12 (±3° from center)
- Variables in era5_2d: TCWV, VAR_2T, SP, ISHF
- Variables in era5_2d_derived: rh_850mb, rh_500mb, w_850mb, w_500mb, q_850mb, q_500mb

Author: Laura Paccini
Date: October 2025
"""

import os
import argparse
import numpy as np
import pandas as pd
import xarray as xr
from glob import glob
import warnings
import sys
from datetime import datetime

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)


def create_circular_mask(x_coords, y_coords, radius_degrees):
    """
    Create a boolean mask for a circular area.
    
    Parameters:
    -----------
    x_coords : np.ndarray
        X coordinates in degrees (east-west offset from center)
    y_coords : np.ndarray
        Y coordinates in degrees (north-south offset from center)
    radius_degrees : float
        Radius of circle in degrees
    
    Returns:
    --------
    np.ndarray (2D boolean)
        Mask where True indicates pixels inside the circle
    """
    # Create 2D grid of coordinates
    x_grid, y_grid = np.meshgrid(x_coords, y_coords)
    
    # Calculate distance from center (0, 0)
    distance = np.sqrt(x_grid**2 + y_grid**2)
    
    # Create mask for points within radius
    mask = distance <= radius_degrees
    
    return mask


def calculate_statistics_for_area(data_array, mask):
    """
    Calculate statistics for data within a circular mask.
    
    Parameters:
    -----------
    data_array : np.ndarray
        2D array of data values
    mask : np.ndarray
        2D boolean mask
    
    Returns:
    --------
    dict
        Dictionary with statistics (mean, median, min, max, std, count, num_valid)
    """
    # Extract values within mask
    masked_values = data_array[mask]
    
    # Remove NaNs and fill values (-999.0 used in era5_2d_derived)
    valid_mask = ~np.isnan(masked_values) & (masked_values > -900)
    valid_values = masked_values[valid_mask]
    
    if len(valid_values) == 0:
        return None
    
    stats = {
        'mean': float(np.mean(valid_values)),
        'median': float(np.median(valid_values)),
        'min': float(np.min(valid_values)),
        'max': float(np.max(valid_values)),
        'std': float(np.std(valid_values)),
        'count': int(np.sum(mask)),
        'num_valid': len(valid_values)
    }
    
    return stats


def load_era5_files(base_dir, variable_name, year_start, year_end, is_2d_derived=False):
    """
    Load ERA5 files for a variable across multiple years.
    
    Parameters:
    -----------
    base_dir : str
        Base directory for ERA5 data
    variable_name : str
        Variable to load
    year_start : int
        Start year
    year_end : int
        End year (inclusive)
    is_2d_derived : bool
        If True, load from era5_2d_derived (multiple files per year)
        If False, load from era5_2d (one file per year)
    
    Returns:
    --------
    xarray.Dataset
        Combined dataset with the variable
    """
    datasets = []
    
    if is_2d_derived:
        # Load from era5_2d_derived (multiple files per year)
        for year in range(year_start, year_end + 1):
            year_dir = os.path.join(base_dir, 'era5_2d_derived', str(year))
            
            if not os.path.exists(year_dir):
                print(f"WARNING: Directory not found: {year_dir}")
                continue
            
            # Find all files for this year
            pattern = f"mcs_era5_2D_ENVS_{year}0101.0000_{year+1}0101.0000_t*.nc"
            files = sorted(glob(os.path.join(year_dir, pattern)))
            
            if len(files) == 0:
                print(f"WARNING: No files found for year {year} in {year_dir}")
                continue
            
            print(f"Loading {len(files)} files for year {year} from era5_2d_derived...")
            
            # Load and combine files
            for file in files:
                try:
                    ds = xr.open_dataset(file)
                    if variable_name in ds:
                        datasets.append(ds[[variable_name]])
                except Exception as e:
                    print(f"WARNING: Failed to load {file}: {e}")
                    continue
    
    else:
        # Load from era5_2d (one file per year)
        for year in range(year_start, year_end + 1):
            filename = f"mcs_era5_{variable_name}_{year}0101.0000_{year+1}0101.0000.nc"
            filepath = os.path.join(base_dir, 'era5_2d', filename)
            
            if not os.path.exists(filepath):
                print(f"WARNING: File not found: {filepath}")
                continue
            
            print(f"Loading {filepath}...")
            
            try:
                ds = xr.open_dataset(filepath)
                datasets.append(ds)
            except Exception as e:
                print(f"WARNING: Failed to load {filepath}: {e}")
                continue
    
    if len(datasets) == 0:
        raise FileNotFoundError(f"No data files found for variable {variable_name}")
    
    # Combine all datasets
    print(f"Combining {len(datasets)} dataset(s)...")
    combined = xr.concat(datasets, dim='tracks')
    
    print(f"Loaded variable '{variable_name}': {combined[variable_name].shape}")
    print(f"  Tracks: {len(combined.tracks)}")
    print(f"  Rel_times: {len(combined.rel_times)}")
    
    return combined


def process_variable(ds, variable_name, radii, track_filter=None, time_freq='1H'):
    """
    Process a single variable and extract statistics for circular areas.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Dataset containing the variable
    variable_name : str
        Name of variable to process
    radii : list
        List of radii in degrees
    track_filter : set, optional
        Set of track IDs to process (if None, process all)
    time_freq : str
        Time frequency for extraction ('1H', '3H', '6H', etc.)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with statistics for all tracks, times, and radii
    """
    print(f"\nProcessing variable: {variable_name}")
    print("="*60)
    
    # Get the data array
    data = ds[variable_name]
    
    # Get coordinates
    x_coords = data.x.values * 0.25  # Convert to degrees
    y_coords = data.y.values * 0.25  # Convert to degrees
    all_rel_times = data.rel_times.values
    tracks = data.tracks.values
    
    print(f"Spatial grid: {len(x_coords)} x {len(y_coords)} points")
    print(f"X range: {x_coords.min():.2f}° to {x_coords.max():.2f}°")
    print(f"Y range: {y_coords.min():.2f}° to {y_coords.max():.2f}°")
    print(f"Available time steps: {len(all_rel_times)} (rel_times: {all_rel_times.min():.1f}h to {all_rel_times.max():.1f}h)")
    print(f"Total tracks: {len(tracks)}")
    
    # Subsample rel_times based on time frequency
    if time_freq != '1H':
        # Parse frequency (e.g., '3H' -> 3)
        freq_hours = int(time_freq.rstrip('Hh'))
        
        # Filter rel_times to match frequency
        # Keep times that are multiples of freq_hours
        rel_times = all_rel_times[all_rel_times % freq_hours == 0]
        
        print(f"Subsampling to {time_freq} frequency: {len(all_rel_times)} → {len(rel_times)} time steps")
        print(f"Selected rel_times: {rel_times[:10]}... (showing first 10)")
    else:
        rel_times = all_rel_times
        print(f"Using all time steps (1H frequency)")
    
    # Filter tracks if specified
    if track_filter is not None:
        tracks_to_process = [t for t in tracks if int(t) in track_filter]
        print(f"Processing {len(tracks_to_process)} filtered tracks")
    else:
        tracks_to_process = tracks
        print(f"Processing all {len(tracks_to_process)} tracks")
    
    # Pre-compute circular masks for each radius
    print(f"\nPre-computing circular masks for radii: {radii}")
    masks = {}
    for radius in radii:
        mask = create_circular_mask(x_coords, y_coords, radius)
        masks[radius] = mask
        pixels_in_circle = np.sum(mask)
        print(f"  Radius {radius}°: {pixels_in_circle} pixels")
    
    # Process each track
    results = []
    total_tracks = len(tracks_to_process)
    total_nan_skipped = 0
    
    print(f"\nExtracting statistics...")
    sys.stdout.flush()
    
    for track_idx, track_id in enumerate(tracks_to_process):
        if track_idx % 1000 == 0 and track_idx > 0:
            print(f"  Progress: {track_idx}/{total_tracks} tracks processed...")
            sys.stdout.flush()
        
        # Get data for this track
        track_data = data.sel(tracks=track_id)
        
        # Process each time step
        for rel_time in rel_times:
            # Get data for this time
            time_data = track_data.sel(rel_times=rel_time).values
            
            # Skip if all NaN or all fill values (track ended before this time)
            # Fill value is -999.0 in era5_2d_derived files
            valid_mask = ~np.isnan(time_data) & (time_data > -900)
            if not np.any(valid_mask):
                total_nan_skipped += 1
                continue
            
            # Calculate statistics for each radius
            for radius in radii:
                mask = masks[radius]
                stats = calculate_statistics_for_area(time_data, mask)
                
                if stats is None:
                    continue
                
                # Store result
                result = {
                    'track_id': int(track_id),
                    'radius': radius,
                    'time_offset_hours': float(rel_time),
                    **stats
                }
                
                results.append(result)
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        result_df = result_df.sort_values(['track_id', 'time_offset_hours', 'radius'])
    
    print(f"\nExtracted {len(result_df)} statistics for {variable_name}")
    print(f"Unique tracks: {result_df['track_id'].nunique()}")
    print(f"Time range: {result_df['time_offset_hours'].min():.1f}h to {result_df['time_offset_hours'].max():.1f}h")
    print(f"Skipped {total_nan_skipped} all-NaN time steps (tracks ended before these times)")
    
    return result_df


def save_results(result_df, output_dir, variable_name, year_start, year_end):
    """
    Save results to parquet file.
    
    Parameters:
    -----------
    result_df : pd.DataFrame
        Results to save
    output_dir : str
        Output directory
    variable_name : str
        Variable name
    year_start : int
        Start year
    year_end : int
        End year
    """
    # Create output directory
    var_output_dir = os.path.join(output_dir, variable_name)
    os.makedirs(var_output_dir, exist_ok=True)
    
    # Create filename
    output_file = os.path.join(
        var_output_dir,
        f"era5_stats_{variable_name}_{year_start}_{year_end}.parquet"
    )
    
    # Save
    result_df.to_parquet(output_file, index=False)
    print(f"Results saved to: {output_file}")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Extract statistics from ERA5 MCS environmental data.'
    )
    
    # Input/output options
    parser.add_argument('--base_dir', 
                        default="/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global",
                        help='Base directory for ERA5 data')
    parser.add_argument('--output_dir', required=True,
                        help='Output directory for results')
    parser.add_argument('--variables', nargs='+', required=True,
                        help='Variable(s) to process')
    
    # Time range
    parser.add_argument('--year_start', type=int, required=True,
                        help='Start year')
    parser.add_argument('--year_end', type=int, required=True,
                        help='End year (inclusive)')
    
    # Processing options
    parser.add_argument('--radii', default="2,3",
                        help='Comma-separated list of radii in degrees')
    parser.add_argument('--time_freq', default='1H',
                        help='Time frequency for extraction (e.g., "1H", "3H", "6H") - extracts rel_times at these intervals')
    
    # Track filtering
    parser.add_argument('--track_list', default=None,
                        help='Path to file with track IDs to process (one per line)')
    
    args = parser.parse_args()
    
    print("="*60)
    print("ERA5 Environmental Variable Statistics Extraction")
    print("="*60)
    print(f"Base directory: {args.base_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Variables: {', '.join(args.variables)}")
    print(f"Year range: {args.year_start} - {args.year_end}")
    print(f"Time frequency: {args.time_freq}")
    print("="*60)
    sys.stdout.flush()
    
    # Parse radii
    try:
        radii = [float(r) for r in args.radii.split(',')]
    except:
        radii = [2.0, 3.0]
    print(f"Using radii: {radii} degrees")
    sys.stdout.flush()
    
    # Load track filter if provided
    track_filter = None
    if args.track_list:
        print(f"Loading track filter from {args.track_list}")
        with open(args.track_list, 'r') as f:
            track_filter = set(int(line.strip()) for line in f if line.strip())
        print(f"Will process {len(track_filter)} tracks")
        sys.stdout.flush()
    
    # Define which variables are in which directory
    era5_2d_vars = ['TCWV', 'VAR_2T', 'SP', 'ISHF']
    era5_2d_derived_vars = ['rh_850mb', 'rh_500mb', 'w_850mb', 'w_500mb', 
                            'q_850mb', 'q_500mb']
    
    # Process each variable
    for var_idx, variable_name in enumerate(args.variables):
        print("\n" + "="*60)
        print(f"Processing variable {var_idx + 1}/{len(args.variables)}: {variable_name}")
        print("="*60)
        sys.stdout.flush()
        
        try:
            # Determine which directory to use
            if variable_name in era5_2d_vars:
                is_2d_derived = False
                print(f"Loading from era5_2d directory")
            elif variable_name in era5_2d_derived_vars:
                is_2d_derived = True
                print(f"Loading from era5_2d_derived directory")
            else:
                print(f"WARNING: Unknown variable '{variable_name}'")
                print(f"Assuming it's in era5_2d_derived...")
                is_2d_derived = True
            
            # Load data
            ds = load_era5_files(
                args.base_dir,
                variable_name,
                args.year_start,
                args.year_end,
                is_2d_derived
            )
            
            # Process variable
            result_df = process_variable(
                ds,
                variable_name,
                radii,
                track_filter,
                args.time_freq
            )
            
            if len(result_df) == 0:
                print(f"WARNING: No data extracted for {variable_name}")
                continue
            
            # Save results
            save_results(
                result_df,
                args.output_dir,
                variable_name,
                args.year_start,
                args.year_end
            )
            
            # Print summary
            print("\n" + "="*60)
            print(f"SUMMARY - {variable_name}")
            print("="*60)
            print(f"Total tracks: {result_df['track_id'].nunique()}")
            print(f"Total data points: {len(result_df)}")
            print(f"Time range: {result_df['time_offset_hours'].min():.1f}h to {result_df['time_offset_hours'].max():.1f}h")
            print(f"Radii: {radii}")
            print("="*60)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"ERROR processing {variable_name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "="*60)
    print("ALL VARIABLES COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main()
