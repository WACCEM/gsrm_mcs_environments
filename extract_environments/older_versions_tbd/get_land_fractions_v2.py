"""
Extract land fraction information for MCS tracks
This script calculates mean land fraction within circular areas around track locations.

This version uses:
- Proven-working sequential approach for circular area calculation
- Optimized batched approach for land fraction extraction 
- Track metadata merged after extraction using simple join operation

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
import time
import warnings
import json
import intake
import sys

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):  # It's a cftime object
        return np.array([np.datetime64(datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])
    return time_array

def calculate_circular_areas_for_tracks(mcs_data, hp_grid, radii, n_workers=4):
    """Calculate circular areas around all MCS track positions for all radii
    
    Parameters:
    -----------
    mcs_data : pandas.DataFrame
        DataFrame with MCS track information including HEALPix indices
    hp_grid : xarray.Dataset
        HEALPix grid with lat/lon information
    radii : np.ndarray
        Array of radii in degrees
    n_workers : int
        Number of worker threads
    
    Returns:
    --------
    dict
        Dictionary mapping (track_id, time_idx, radius) to pixel arrays
    """
    # Get HEALPix grid parameters
    nside = egh.get_nside(hp_grid)
    nest = True if egh.get_nest(hp_grid) else False
    
    # Dictionary to store all circular areas
    all_areas = {}
    
    # Process tracks in batches for memory efficiency
    batch_size = 200
    total_tracks = len(mcs_data)
    
    def process_track_batch(batch_data):
        """Process a batch of tracks"""
        batch_areas = {}
        
        for _, row in batch_data.iterrows():
            track_id = row.name[0] if isinstance(row.name, tuple) else row.name
            time_idx = row.name[1] if isinstance(row.name, tuple) else 0
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
                
                batch_areas[(track_id, time_idx, radius)] = area_pixels
        
        return batch_areas
    
    print(f"Calculating circular areas for {total_tracks} track positions...")
    
    for batch_start in range(0, total_tracks, batch_size):
        batch_end = min(batch_start + batch_size, total_tracks)
        batch_data = mcs_data.iloc[batch_start:batch_end]
        if batch_start % 100000 == 0 and batch_start > 0:
            print(f"  Progress: {batch_start}/{total_tracks} areas processed...")
            sys.stdout.flush()

        # Process batch
        batch_areas = process_track_batch(batch_data)
        all_areas.update(batch_areas)
    
    print(f"Calculated circular areas for {len(all_areas)} track-time-radius combinations")
    return all_areas

def extract_land_fractions_efficient(all_areas, land_fraction_data, radii, mcs_data,n_workers=4, is_ocean_fraction=False):
    """Extract land fraction statistics for all circular areas
    
    Parameters:
    -----------
    all_areas : dict
        Dictionary mapping (track_id, time_idx, radius) to pixel arrays
    land_fraction_data : xarray.DataArray
        Land fraction data
    radii : np.ndarray
        Array of radii in degrees
    mcs_data : pandas.DataFrame
        DataFrame with MCS track information
    n_workers : int
        Number of worker threads
    is_ocean_fraction : bool
        True if input data is ocean fraction, False if land fraction
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with land fraction statistics for each track, time, and radius
    """
    results = []
    
    # Get all unique pixels needed
    all_pixels = set()
    for pixels in all_areas.values():
        all_pixels.update(pixels)
    all_pixels = list(all_pixels)
    
    print(f"Loading land fraction data for {len(all_pixels)} unique pixels...")
    
    # Load land fraction data for all needed pixels at once
    try:
        lf_data = land_fraction_data.sel(cell=all_pixels).compute()
    except Exception as e:
        print(f"Error loading land fraction data: {e}")
        return pd.DataFrame()
    
    # Process areas in batches
    batch_size = 500
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"Processing land fractions for {total_areas} areas...")
    
    for batch_start in range(0, total_areas, batch_size):
        batch_end = min(batch_start + batch_size, total_areas)
        batch_keys = area_keys[batch_start:batch_end]
        
        print(f"Processing batch {batch_start//batch_size + 1}/{(total_areas//batch_size) + 1}")
        
        for area_key in batch_keys:
            track_id, time_idx, radius = area_key
            pixels = all_areas[area_key]
            
            # Get corresponding track data
            try:
                if isinstance(mcs_data.index[0], tuple):
                    track_data = mcs_data.loc[(track_id, time_idx)]
                else:
                    # For single-time tracks, find the track
                    track_data = mcs_data.loc[track_id]
            except KeyError:
                continue
            
            # Extract land fraction for this area
            try:
                area_fraction_values = lf_data.sel(cell=pixels).values

                # Convert to land fraction if input is ocean fraction
                if is_ocean_fraction:
                    # Convert ocean fraction to land fraction (assuming percentages)
                    area_lf_values = 1 - area_fraction_values
                else:
                    area_lf_values = area_fraction_values
                
                # CRITICAL FIX: Treat NaN as 0.0 (ocean) instead of invalid data
                # This is necessary because land fraction is NaN over ocean in ICON/UM models
                area_lf_with_ocean = np.where(np.isnan(area_lf_values), 0.0, area_lf_values)
                
                # Calculate land fraction over the circular area
                mean_lf = float(np.mean(area_lf_with_ocean))
                num_land_pixels = int(np.sum(area_lf_with_ocean > 0))
                
                # Create result record
                result = {
                    'track_id': track_id,
                    'time_idx': time_idx,
                    'radius': radius,
                    'mean_land_fraction': mean_lf,
                    'num_land_pixels': num_land_pixels,
                    # Add track metadata
                    'base_time': track_data['base_time'] if 'base_time' in track_data else pd.NaT,
                    'start_basetime': track_data['start_basetime'] if 'start_basetime' in track_data else pd.NaT,
                    'meanlat': track_data['meanlat'] if 'meanlat' in track_data else np.nan,
                    'meanlon': track_data['meanlon'] if 'meanlon' in track_data else np.nan,
                    'track_duration': track_data['track_duration'] if 'track_duration' in track_data else np.nan,
                    'mcs_duration': track_data['mcs_duration'] if 'mcs_duration' in track_data else np.nan,
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"Error processing area {area_key}: {e}")
                continue
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    # if len(result_df) > 0:
    #     # Sort by track_id, time_idx, radius for easier access
    #     result_df = result_df.sort_values(['track_id', 'time_idx', 'radius'])
        
    #     # Add derived columns
    #     result_df['is_ocean'] = result_df['mean_land_fraction'] < ocean_threshold  # 10% threshold
    #     result_df['is_mostly_ocean'] = result_df['ocean_fraction'] > ocean_fraction_threshold  # 50% ocean threshold
    
    print(f"Extracted land fractions for {len(result_df)} track-time-radius combinations")
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
            'start_basetime': group['start_basetime'].iloc[0],
            'track_duration': group['track_duration'].iloc[0],
            'mcs_duration': group['mcs_duration'].iloc[0],
            'start_lat': group['meanlat'].iloc[0],  # Use first time point as start
            'start_lon': group['meanlon'].iloc[0],
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
    parser.add_argument('--n_workers', type=int, default=4, help='Number of worker threads')
    
    # Ocean/land threshold options
    parser.add_argument('--ocean_threshold', type=float, default=0.1,
                        help='Maximum land fraction to consider as ocean (0.0-1.0, default: 0.1 = 10%)')
    parser.add_argument('--ocean_fraction_threshold', type=float, default=0.5,
                        help='Minimum fraction of ocean pixels to consider mostly ocean (0.0-1.0, default: 0.5 = 50%)')
    
    # Add new argument for ocean fraction handling
    parser.add_argument('--is_ocean_fraction', action='store_true',
                        help='Set this flag if the input variable is ocean fraction instead of land fraction')


    args = parser.parse_args()
    
    # Start timing
    start_time = time.time()
    
    print(f"Starting land fraction extraction for MCS tracks...")
    print(f"Using land fraction variable: {args.land_fraction_var}")
    
    # Parse RADII from command line
    try:
        RADII = np.array([float(r) for r in args.radii.split(',')])
    except:
        RADII = np.array([5.0, 3.5, 2.0, 0.5])
    print(f"Using radii: {RADII}")
    
    # Determine if we're using ocean fraction
    is_ocean_fraction = args.is_ocean_fraction or 'ocean' in args.land_fraction_var.lower()
    
    print(f"Using {'ocean' if is_ocean_fraction else 'land'} fraction variable: {args.land_fraction_var}")

    # Parse catalog parameters
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        print(f"Warning: Could not parse catalog_params. Using default zoom=8.")
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    # Open catalog and get dataset
    print(f"Opening catalog from {args.catalog_url}")
    cat = intake.open_catalog(args.catalog_url)[args.current_location]
    
    # Load dataset
    print(f"Loading dataset {args.catalog_model} from catalog...")
    ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(egh.attach_coords, signed_lon=True)
    ds = ds.assign_coords(time=convert_time(ds.time.values))
    
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
    
    # Load land fraction data
    print(f"Loading land fraction data ({args.land_fraction_var})...")
    try:
        land_fraction_data = ds_filtered[args.land_fraction_var].compute()
    except KeyError:
        print(f"Error: Land fraction variable '{args.land_fraction_var}' not found in dataset")
        print(f"Available variables: {list(ds_filtered.data_vars.keys())}")
        return
    
    # Load MCS track data
    print(f"Loading MCS track data from {args.trackfile}")
    mcs_trackstats = xr.open_dataset(args.trackfile)
    
    # Get relevant variables
    required_vars = ['start_split_cloudnumber', 'start_basetime', 'base_time', 
                     'meanlon', 'meanlat', 'mcs_status', 'track_duration', 'mcs_duration']
    
    # Check which variables are available
    available_vars = [var for var in required_vars if var in mcs_trackstats]
    if len(available_vars) < len(required_vars):
        missing_vars = set(required_vars) - set(available_vars)
        print(f"Warning: Missing variables in track file: {missing_vars}")
    
    subset_mcs_stats = mcs_trackstats[available_vars].compute()
    
    # Convert to DataFrame
    df = subset_mcs_stats.to_dataframe()
    
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
    print(f"Filtered to {len(filtered_df)} track time points")
    
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
    
    # Calculate circular areas for all tracks
    all_areas = calculate_circular_areas_for_tracks(
        filtered_df, hp_grid, RADII, n_workers=args.n_workers
    )
    
    # Extract land fraction statistics
    land_fraction_df = extract_land_fractions_efficient(
        all_areas, land_fraction_data, RADII, filtered_df, n_workers=args.n_workers,
        is_ocean_fraction=is_ocean_fraction
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
        ocean_tracks = radius_data['is_ocean_track'].sum()
        print(f"  Radius {radius}°: {ocean_tracks}/{len(radius_data)} tracks are ocean-only")
    
    # Print timing information
    elapsed_time = time.time() - start_time
    print(f"\nExtraction completed in {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    
    return detailed_path, summary_path

if __name__ == "__main__":
    main()