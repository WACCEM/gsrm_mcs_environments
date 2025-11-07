"""
Extract land fraction information for MCS tracks

This script calculates mean land fraction within circular areas around track locations.
Optimized for memory efficiency using streaming data access.

Key features:
- Streaming data loading prevents memory overflow on high-resolution grids
- Computes mean land fraction over circular areas at multiple radii
- Generates per-track and per-radius summary statistics

Author: Laura Paccini
Last updated: October 2025
"""
import os
import argparse
import numpy as np
import pandas as pd
import xarray as xr
import healpy as hp
from easygems import healpix as egh
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import warnings
import json
import intake

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)

print("DEBUG: Imports completed, script loaded successfully")
import sys
sys.stdout.flush()

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):  # It's a cftime object
        return np.array([np.datetime64(datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])
    return time_array

def calculate_circular_areas_for_tracks(mcs_data, hp_grid, radii):
    """Calculate circular areas around all MCS track positions for all radii
    
    Parameters:
    -----------
    mcs_data : pandas.DataFrame
        DataFrame with MCS track information including HEALPix indices
    hp_grid : xarray.Dataset
        HEALPix grid with lat/lon information
    radii : np.ndarray
        Array of radii in degrees
    
    Returns:
    --------
    dict
        Dictionary mapping (track_id, time_idx, radius) to pixel arrays
    """
    print("DEBUG: Entered calculate_circular_areas_for_tracks()")
    sys.stdout.flush()
    
    # Get HEALPix grid parameters
    nside = egh.get_nside(hp_grid)
    nest = True if egh.get_nest(hp_grid) else False
    
    print(f"DEBUG: Got nside={nside}, nest={nest}")
    sys.stdout.flush()
    
    # Dictionary to store all circular areas
    all_areas = {}
    
    total_points = len(mcs_data)
    print(f"Calculating circular areas for {total_points} track positions...")
    print(f"DEBUG: About to start iterrows() loop")
    sys.stdout.flush()
    
    for idx, row in mcs_data.iterrows():
        if idx % 10000 == 0:
            print(f"  Progress: {idx}/{total_points} positions processed...")
            
        track_id = int(row['tracks'])
        time_idx = int(row['times'])
        cell_idx = int(row['trigger_idx'])
        
        # Calculate areas for all radii
        for radius in radii:
            # Get pixels within radius
            area_pixels = hp.query_disc(
                nside, 
                hp.pix2vec(nside, cell_idx, nest=nest), 
                np.radians(radius),
                inclusive=False, 
                nest=nest
            )
            
            all_areas[(track_id, time_idx, radius)] = area_pixels
    
    print(f"Calculated circular areas for {len(all_areas)} track-time-radius combinations")
    return all_areas

def extract_land_fractions_efficient(all_areas, land_fraction_data, mcs_data, n_workers=4, 
                                   is_ocean_fraction=False, use_streaming=False):
    """Extract land fraction statistics for all circular areas
    
    Can use either parallel processing (faster, memory-intensive) or streaming (slower, memory-efficient).
    
    Parameters:
    -----------
    all_areas : dict
        Dictionary mapping (track_id, time_idx, radius) to pixel arrays
    land_fraction_data : xarray.DataArray
        Land fraction data (lazy-loaded for streaming, can be computed for parallel)
    mcs_data : pandas.DataFrame
        DataFrame with MCS track information
    n_workers : int
        Number of worker threads (only used when use_streaming=False)
    is_ocean_fraction : bool
        True if input data is ocean fraction, False if land fraction
    use_streaming : bool
        If True: streaming mode (memory-efficient, recommended for zoom 10+)
        If False: parallel mode (faster, works for zoom <10)
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with land fraction statistics for each track, time, and radius
    """
    total_areas = len(all_areas)
    
    if use_streaming:
        print(f"Processing {total_areas} areas with STREAMING mode (memory-efficient)...")
        return _extract_with_streaming(all_areas, land_fraction_data, mcs_data, is_ocean_fraction)
    else:
        print(f"Processing {total_areas} areas with PARALLEL mode (faster)...")
        return _extract_with_parallel(all_areas, land_fraction_data, mcs_data, n_workers, is_ocean_fraction)


def _extract_with_streaming(all_areas, land_fraction_data, mcs_data, is_ocean_fraction=False):
    """Streaming approach: load data per area (memory-efficient for high-res grids)"""
    results = []
    total_areas = len(all_areas)
    
    # Process each area individually with streaming data loading
    # This prevents memory overflow by loading only needed pixels per area
    for idx, (area_key, pixels) in enumerate(all_areas.items()):
        if idx % 1000 == 0:
            print(f"  Progress: {idx}/{total_areas} areas processed...")
            
        track_id, time_idx, radius = area_key
        
        # Get corresponding track data
        try:
            # Find the matching row in mcs_data
            mask = (mcs_data['tracks'] == track_id) & (mcs_data['times'] == time_idx)
            if not mask.any():
                continue
            track_data = mcs_data[mask].iloc[0]
        except (KeyError, IndexError):
            continue
        
        # Extract land fraction for this area with streaming data loading
        try:
            # Load land fraction data for ONLY this area's pixels (prevents memory overflow)
            area_fraction_values = land_fraction_data.sel(cell=pixels).compute().values
            
            # Filter out NaN values
            valid_mask = ~np.isnan(area_fraction_values)
            valid_fractions = area_fraction_values[valid_mask]
            
            if len(valid_fractions) == 0:
                continue

            # Convert to land fraction if input is ocean fraction
            if is_ocean_fraction:
                land_fractions = 1.0 - valid_fractions
            else:
                land_fractions = valid_fractions
            
            # Calculate mean land fraction over the circular area
            mean_lf = float(np.mean(land_fractions))
            
            # Create result record
            result = {
                'track_id': int(track_id),
                'time_idx': int(time_idx),
                'radius': radius,
                'mean_land_fraction': mean_lf,
                'num_pixels': len(land_fractions),
                # Add track metadata
                'base_time': track_data['base_time'] if 'base_time' in track_data else pd.NaT,
                # 'start_basetime': track_data['start_basetime'] if 'start_basetime' in track_data else pd.NaT,
                # 'track_duration': track_data['track_duration'] if 'track_duration' in track_data else np.nan,
                'meanlat': track_data['meanlat'] if 'meanlat' in track_data else np.nan,
                'meanlon': track_data['meanlon'] if 'meanlon' in track_data else np.nan,
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"  Warning: Error processing area {area_key}: {e}")
            continue
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        # Sort by track_id, time_idx, radius for easier access
        result_df = result_df.sort_values(['track_id', 'time_idx', 'radius'])
    
    print(f"Extracted land fractions for {len(result_df)} track-time-radius combinations")
    return result_df


def _extract_with_parallel(all_areas, land_fraction_data, mcs_data, n_workers=4, is_ocean_fraction=False):
    """Parallel approach: load all data at once (faster but memory-intensive for low-res grids)"""
    
    # Get all unique pixels needed
    all_pixels = set()
    for pixels in all_areas.values():
        all_pixels.update(pixels)
    all_pixels = list(all_pixels)
    
    print(f"  Loading land fraction data for {len(all_pixels)} unique pixels...")
    
    # Load land fraction data for all needed pixels at once
    try:
        lf_data = land_fraction_data.sel(cell=all_pixels).compute()
        print(f"  Successfully loaded land fraction data.")
    except Exception as e:
        print(f"  ERROR: Failed to load land fraction data: {e}")
        print(f"  TIP: Try using --use_streaming flag for high-resolution grids")
        return pd.DataFrame()
    
    # Process areas using ThreadPoolExecutor for actual parallelism
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"  Processing {total_areas} areas with {n_workers} workers...")
    
    def process_area(area_key):
        """Process a single area and return result dict or None"""
        track_id, time_idx, radius = area_key
        pixels = all_areas[area_key]
        
        # Get corresponding track data
        try:
            mask = (mcs_data['tracks'] == track_id) & (mcs_data['times'] == time_idx)
            if not mask.any():
                return None
            track_data = mcs_data[mask].iloc[0]
        except (KeyError, IndexError):
            return None
        
        # Extract land fraction for this area
        try:
            area_fraction_values = lf_data.sel(cell=pixels).values
            
            # Filter out NaN values
            valid_mask = ~np.isnan(area_fraction_values)
            valid_fractions = area_fraction_values[valid_mask]
            
            if len(valid_fractions) == 0:
                return None

            # Convert to land fraction if input is ocean fraction
            if is_ocean_fraction:
                land_fractions = 1.0 - valid_fractions
            else:
                land_fractions = valid_fractions
            
            # Calculate mean land fraction over the circular area
            mean_lf = float(np.mean(land_fractions))
            
            # Create result record
            result = {
                'track_id': int(track_id),
                'time_idx': int(time_idx),
                'radius': radius,
                'mean_land_fraction': mean_lf,
                'num_pixels': len(land_fractions),
                # Add track metadata
                'base_time': track_data['base_time'] if 'base_time' in track_data else pd.NaT,
                # 'start_basetime': track_data['start_basetime'] if 'start_basetime' in track_data else pd.NaT,
                # 'track_duration': track_data['track_duration'] if 'track_duration' in track_data else np.nan,
                'meanlat': track_data['meanlat'] if 'meanlat' in track_data else np.nan,
                'meanlon': track_data['meanlon'] if 'meanlon' in track_data else np.nan,
            }
            
            return result
            
        except Exception as e:
            return None
    
    # Use ThreadPoolExecutor for parallel processing
    results = []
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_area, key): key for key in area_keys}
        
        # Process results as they complete
        from concurrent.futures import as_completed
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
            
            processed_count += 1
            if processed_count % 50000 == 0:
                print(f"    Progress: {processed_count}/{total_areas} areas processed...")
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        # Sort by track_id, time_idx, radius for easier access
        result_df = result_df.sort_values(['track_id', 'time_idx', 'radius'])
    
    print(f"  Extracted land fractions for {len(result_df)} track-time-radius combinations")
    return result_df


def calculate_track_summary_statistics(land_fraction_df):
    """Calculate summary statistics for each track across all times
    
    Parameters:
    -----------
    land_fraction_df : pandas.DataFrame
        DataFrame with land fraction data for all track-time-radius combinations
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with summary statistics for each track-radius combination
    """
    print("Calculating track summary statistics...")
    
    if len(land_fraction_df) == 0:
        print("Warning: No data to calculate summary statistics")
        return pd.DataFrame()
    
    # Group by track_id and radius
    summary_stats = []
    
    for (track_id, radius), group in land_fraction_df.groupby(['track_id', 'radius']):
        # Calculate statistics across all times for this track-radius combination
        stats = {
            'track_id': track_id,
            'radius': radius,
            'mean_land_fraction_track': group['mean_land_fraction'].mean(),
            'total_land_fraction_track': group['mean_land_fraction'].sum(),
            'num_time_points': len(group),
            # Track metadata (should be the same for all time points)
            # 'start_basetime': group['start_basetime'].iloc[0] if 'start_basetime' in group else pd.NaT,
            # 'track_duration': group['track_duration'].iloc[0] if 'track_duration' in group else np.nan,
            'start_lat': group['meanlat'].iloc[0] if 'meanlat' in group else np.nan,
            'start_lon': group['meanlon'].iloc[0] if 'meanlon' in group else np.nan,
        }
        
        summary_stats.append(stats)
    
    summary_df = pd.DataFrame(summary_stats)
    
    print(f"Created summary statistics for {len(summary_df)} track-radius combinations")
    return summary_df

def save_land_fraction_data(land_fraction_df, summary_df, output_dir, output_format='netcdf', model_name=None, zoom_name=None):
    """Save land fraction data to files
    
    Parameters:
    -----------
    land_fraction_df : pandas.DataFrame
        DataFrame with detailed land fraction data
    summary_df : pandas.DataFrame
        DataFrame with summary statistics
    output_dir : str
        Output directory
    output_format : str
        Format to save files ('netcdf', 'parquet', 'csv')
    model_name : str
        Name of the model to include in filename
    zoom_name: str or int
        Name of the zoom level to include in filename
    """
    os.makedirs(output_dir, exist_ok=True)

    # Create base filename with model name
    if model_name and zoom_name:
        base_filename = f'mcs_land_fractions_{model_name}_zoom{zoom_name}'
    else:
        base_filename = 'mcs_land_fractions'
    
    # Save detailed data
    detailed_path = os.path.join(output_dir, f'{base_filename}_detailed')
    if output_format == 'netcdf':
        detailed_path += '.nc'
        land_fraction_df.to_xarray().to_netcdf(detailed_path)
    elif output_format == 'parquet':
        detailed_path += '.parquet'
        land_fraction_df.to_parquet(detailed_path, index=False)
    elif output_format == 'csv':
        detailed_path += '.csv'
        land_fraction_df.to_csv(detailed_path, index=False)
    
    # Save summary data
    summary_path = os.path.join(output_dir, f'{base_filename}_summary')
    if output_format == 'netcdf':
        summary_path += '.nc'
        summary_df.to_xarray().to_netcdf(summary_path)
    elif output_format == 'parquet':
        summary_path += '.parquet'
        summary_df.to_parquet(summary_path, index=False)
    elif output_format == 'csv':
        summary_path += '.csv'
        summary_df.to_csv(summary_path, index=False)
    
    print(f"Saved detailed land fraction data to {detailed_path}")
    print(f"Saved summary land fraction data to {summary_path}")
    
    return detailed_path, summary_path

def main():
    print("DEBUG: Entered main() function")
    sys.stdout.flush()
    
    parser = argparse.ArgumentParser(description='Extract land fraction information for MCS tracks.')
    
    # Input/output options
    parser.add_argument('--catalog_url', 
                        default="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml",
                        help='URL of the intake catalog')
    parser.add_argument('--current_location', default="NERSC", help='Current location in catalog')
    parser.add_argument('--catalog_model', default="scream_ne120", 
                        help='Model name in the catalog')
    parser.add_argument('--catalog_params', default='{"zoom": 8}', 
                        help='JSON string of catalog parameters')
    parser.add_argument('--trackfile', required=True, help='Path to MCS track file')
    parser.add_argument('--output_dir', required=True, help='Output directory for results')
    parser.add_argument('--output_format', default='netcdf', choices=['parquet', 'csv', 'netcdf'],
                        help='Format to save results')
    
    # Land fraction variable name (model-specific)
    parser.add_argument('--land_fraction_var', default='LANDFRAC', 
                        help='Name of land fraction variable in the model dataset')
    
    # Date filtering options
    parser.add_argument('--start_date', help='Start date for filtering (YYYY-MM-DD)')
    parser.add_argument('--end_date', help='End date for filtering (YYYY-MM-DD)')
    
    # Spatial filtering options
    parser.add_argument('--min_lon', type=float, default=None, help='Minimum longitude')
    parser.add_argument('--max_lon', type=float, default=None, help='Maximum longitude')
    parser.add_argument('--min_lat', type=float, default=None, help='Minimum latitude')
    parser.add_argument('--max_lat', type=float, default=None, help='Maximum latitude')
    
    # Processing options
    parser.add_argument('--radii', default="5,3.5,2,0.5", 
                        help='Comma-separated list of radii in degrees')
    parser.add_argument('--lat_var', default='meanlat', help='Latitude variable name in tracks')
    parser.add_argument('--lon_var', default='meanlon', help='Longitude variable name in tracks')
    parser.add_argument('--n_workers', type=int, default=4, 
                        help='Number of worker threads (only used with parallel processing, not streaming)')
    parser.add_argument('--use_streaming', action='store_true',
                        help='Use streaming mode (slower but memory-efficient). Recommended for zoom 10+')
    
    # Ocean/land threshold options
    parser.add_argument('--ocean_threshold', type=float, default=0.1,
                        help='Maximum land fraction to consider as ocean (0.0-1.0, default: 0.1 = 10%)')
    parser.add_argument('--ocean_fraction_threshold', type=float, default=0.5,
                        help='Minimum fraction of ocean pixels to consider mostly ocean (0.0-1.0, default: 0.5 = 50%)')
    
    # Add new argument for ocean fraction handling
    parser.add_argument('--is_ocean_fraction', action='store_true',
                        help='Set this flag if the input variable is ocean fraction instead of land fraction')


    args = parser.parse_args()
    
    print("DEBUG: Arguments parsed successfully")
    sys.stdout.flush()
    
    print("DEBUG: Step A")
    sys.stdout.flush()
    
    # Start timing
    start_time = time.time()
    
    print("DEBUG: Step B - about to print with f-string")
    sys.stdout.flush()
    
    print(f"Starting land fraction extraction for MCS tracks...")
    
    print("DEBUG: Step C - first f-string worked")
    sys.stdout.flush()
    
    print(f"Using land fraction variable: {args.land_fraction_var}")
    
    print("DEBUG: Step D - second f-string worked")
    sys.stdout.flush()
    
    # Parse RADII from command line
    print("DEBUG: Step E - about to parse RADII")
    sys.stdout.flush()
    try:
        RADII = np.array([float(r) for r in args.radii.split(',')])
    except:
        RADII = np.array([5.0, 3.5, 2.0, 0.5])
    print(f"Using radii: {RADII}")
    
    print("DEBUG: Step F - RADII parsed")
    sys.stdout.flush()
    
    # Parse catalog parameters to detect zoom level
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        print(f"Warning: Could not parse catalog_params. Using default zoom=8.")
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    print("DEBUG: Step G - catalog params parsed")
    sys.stdout.flush()    # Determine if we're using ocean fraction
    is_ocean_fraction = args.is_ocean_fraction or 'ocean' in args.land_fraction_var.lower()
    
    print(f"Using {'ocean' if is_ocean_fraction else 'land'} fraction variable: {args.land_fraction_var}")
    
    # Auto-recommend streaming for high-res grids
    if not args.use_streaming and zoom_level >= 10:
        print(f"\n⚠️  WARNING: Detected high-resolution grid (zoom {zoom_level})")
        print(f"    Consider using --use_streaming flag to prevent memory issues")
        print(f"    Proceeding with parallel processing (may cause OOM errors)...\n")
    elif args.use_streaming:
        print(f"Using STREAMING mode for zoom {zoom_level} (memory-efficient)")
    else:
        print(f"Using PARALLEL mode for zoom {zoom_level} (faster)")

    # Open catalog and get dataset
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        print(f"Warning: Could not parse catalog_params. Using default zoom=8.")
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    # Open catalog and get dataset
    print(f"DEBUG: Step H - About to call intake.open_catalog({args.catalog_url})")
    sys.stdout.flush()
    
    print(f"Opening catalog from {args.catalog_url}")
    cat = intake.open_catalog(args.catalog_url)[args.current_location]
    
    print(f"DEBUG: Step I - Catalog opened successfully!")
    sys.stdout.flush()
    
    # Load dataset
    print(f"Loading dataset {args.catalog_model} from catalog...")
    ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(egh.attach_coords, signed_lon=True)
    # NOTE: Don't convert time coords - not needed and very expensive!
    # ds = ds.assign_coords(time=convert_time(ds.time.values))
    print(f"DEBUG: Step L - Catalog loaded")
    sys.stdout.flush()
    # Set spatial bounds
    if args.min_lat is None:
        min_lat = -90 + RADII.max()
    else:
        min_lat = args.min_lat
    
    if args.max_lat is None:
        max_lat = 90 - RADII.max()
    else:
        max_lat = args.max_lat
    
    lat_bounds = (min_lat, max_lat)
    print(f"Using latitude bounds: {lat_bounds}")
    
    
    ds_filtered = ds.copy()
    # Get HEALPix grid coordinates
    print("Computing HEALPix grid...")
    hp_grid = ds_filtered[['lat', 'lon']].compute()
    print(f"DEBUG: Step M - HEALPix grid computed")
    sys.stdout.flush()
    # Load land fraction data (keep lazy for streaming access)
    print(f"Setting up land fraction data ({args.land_fraction_var}) for streaming access...")
    try:
        land_fraction_data = ds_filtered[args.land_fraction_var]  # Keep lazy, don't compute!
    except KeyError:
        print(f"Error: Land fraction variable '{args.land_fraction_var}' not found in dataset")
        print(f"Available variables: {list(ds_filtered.data_vars.keys())}")
        return
    
    # Load MCS track data
    print(f"Loading MCS track data from {args.trackfile}")
    mcs_trackstats = xr.open_dataset(args.trackfile)
    print(f"DEBUG: Step N - MCS track data loaded")
    sys.stdout.flush()
    # Get relevant variables
    required_vars = ['meanlon', 'meanlat', 'base_time']
    
    # Check which variables are available
    available_vars = [var for var in required_vars if var in mcs_trackstats]
    if len(available_vars) < len(required_vars):
        missing_vars = set(required_vars) - set(available_vars)
        print(f"Warning: Missing variables in track file: {missing_vars}")
    
    subset_mcs_stats = mcs_trackstats[available_vars].compute()
    
    # Convert to DataFrame and reset index to make tracks/times regular columns
    df = subset_mcs_stats.to_dataframe().reset_index()
    
    # Filter out rows with NaN lat/lon (invalid time steps beyond track duration)
    df = df.dropna(subset=[args.lat_var, args.lon_var])
    print(f"After dropping NaN positions: {len(df)} valid track time points")
    
    print(f"DEBUG: Step O - converted to DataFrame")
    sys.stdout.flush()

    # Apply filters
    filter_conditions = [
        df[args.lat_var].between(lat_bounds[0], lat_bounds[1]),
        df[args.lat_var].notna(),
        df[args.lon_var].notna()
    ]
    
    # Add date filters
    if args.start_date:
        start_date = pd.Timestamp(args.start_date)
        filter_conditions.append(pd.to_datetime(df['base_time']) >= start_date)
    
    if args.end_date:
        end_date = pd.Timestamp(args.end_date)
        filter_conditions.append(pd.to_datetime(df['base_time']) <= end_date)
    
    # Add longitude filters
    if args.min_lon is not None and args.max_lon is not None:
        if args.min_lon > args.max_lon:
            filter_conditions.append((df[args.lon_var] >= args.min_lon) | 
                                    (df[args.lon_var] <= args.max_lon))
        else:
            filter_conditions.append(df[args.lon_var].between(args.min_lon, args.max_lon))
    
    # Apply filters
    filtered_df = df[np.logical_and.reduce(filter_conditions)].copy()

    # Reset index to make it sequential (critical for iterrows performance!)
    filtered_df = filtered_df.reset_index(drop=True)
    
    print(f"Filtered to {len(filtered_df)} track time points")
    
    print(f"DEBUG: Step P - filtered DataFrame")
    sys.stdout.flush()

    # Calculate HEALPix indices
    print("Calculating HEALPix indices...")
    nside = egh.get_nside(hp_grid)
    pixel_indices = hp.ang2pix(
        nside,
        filtered_df[args.lon_var].values,
        filtered_df[args.lat_var].values,
        nest=True, 
        lonlat=True
    )
    filtered_df['trigger_idx'] = pixel_indices

    print(f"DEBUG: Step Q - HEALPix indices calculated and ready to enter area calculation")
    sys.stdout.flush()

    # Calculate circular areas for all tracks
    all_areas = calculate_circular_areas_for_tracks(
        filtered_df, hp_grid, RADII
    )
    
    # Extract land fraction statistics
    land_fraction_df = extract_land_fractions_efficient(
        all_areas, land_fraction_data, filtered_df, 
        n_workers=args.n_workers,
        is_ocean_fraction=is_ocean_fraction,
        use_streaming=args.use_streaming
    )
    
    # Calculate summary statistics
    summary_df = calculate_track_summary_statistics(land_fraction_df)
    
    # Save results
    detailed_path, summary_path = save_land_fraction_data(
        land_fraction_df, summary_df, args.output_dir, args.output_format, 
        model_name=args.catalog_model, zoom_name=zoom_level
    )
    
    # Print summary statistics
    print("\n=== SUMMARY STATISTICS ===")
    print(f"Total tracks processed: {len(summary_df['track_id'].unique())}")
    print(f"Total track-time points: {len(land_fraction_df)}")
    print(f"Radii processed: {RADII}")
    
    for radius in RADII:
        radius_data = summary_df[summary_df['radius'] == radius]
        mean_lf = radius_data['mean_land_fraction_track'].mean()
        print(f"  Radius {radius}°: {len(radius_data)} tracks, mean land fraction = {mean_lf:.3f}")
    
    # Print timing information
    elapsed_time = time.time() - start_time
    print(f"\nExtraction completed in {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    
    return detailed_path, summary_path

if __name__ == "__main__":
    main()