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
    if hasattr(time_array[0], 'year'):
        return np.array([np.datetime64(datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])
    return time_array


def calculate_circular_areas_sequential(mcs_data, hp_grid, radii, progress_freq=50000):
    """
    Calculate circular areas using the proven sequential approach from test script.
    (fastest method based on benchmarking.)
    """
    nside = egh.get_nside(hp_grid)
    nest = True
    all_areas = {}
    total_points = len(mcs_data)
    
    print(f"Calculating circular areas for {total_points} track positions...")
    sys.stdout.flush()
    
    
    for idx, row in mcs_data.iterrows():
        if idx % progress_freq == 0:
            print(f"  Progress: {idx}/{total_points} positions processed...")
            sys.stdout.flush()
            
        track_id = int(row['tracks'])
        time_idx = int(row['times'])
        cell_idx = int(row['trigger_idx'])
        
        for radius in radii:
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


def extract_land_fractions_batched(all_areas, land_fraction_data, batch_size=500):
    """
    Extract land fraction statistics for all circular areas using batched processing.
    
    This is the optimized version that extracts land fractions from pixels.
    """
    
    # Get all unique pixels needed
    all_pixels = set()
    for pixels in all_areas.values():
        all_pixels.update(pixels)
    all_pixels = list(all_pixels)
    
    print(f"Loading land fraction data for {len(all_pixels)} unique pixels...")
    sys.stdout.flush()
    
    # Load land fraction data for all needed pixels at once
    try:
        lf_data = land_fraction_data.sel(cell=all_pixels).compute()
        print(f"Successfully loaded land fraction data.")
        sys.stdout.flush()
    except Exception as e:
        print(f"ERROR: Failed to load land fraction data: {e}")
        return pd.DataFrame()
    
    # Process areas in batches
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"Processing {total_areas} areas with batched approach (batch_size={batch_size})...")
    sys.stdout.flush()
    
    results = []
    
    for batch_start in range(0, total_areas, batch_size):
        batch_end = min(batch_start + batch_size, total_areas)
        batch_keys = area_keys[batch_start:batch_end]
        
        if batch_start % 100000 == 0 and batch_start > 0:
            print(f"  Progress: {batch_start}/{total_areas} areas processed...")
            sys.stdout.flush()
        
        for area_key in batch_keys:
            track_id, time_idx, radius = area_key
            pixels = all_areas[area_key]
            
            # Extract land fraction for this area 
            try:
                area_fraction_values = lf_data.sel(cell=pixels).values

                area_fraction_values = np.where(np.isnan(area_fraction_values), 0.0, area_fraction_values)
                # valid_fractions = area_fraction_values[~np.isnan(area_fraction_values)]
                
                if len(area_fraction_values) == 0:
                    continue
                
                mean_lf = float(np.mean(area_fraction_values))
                
                # Store minimal result 
                result = {
                    'track_id': int(track_id),
                    'time_idx': int(time_idx),
                    'radius': radius,
                    'mean_land_fraction': mean_lf,
                    'num_pixels': len(area_fraction_values),
                }
                
                results.append(result)
                
            except Exception as e:
                continue
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        result_df = result_df.sort_values(['track_id', 'time_idx', 'radius'])
    
    print(f"Extracted land fractions for {len(result_df)} track-time-radius combinations")
    sys.stdout.flush()
    return result_df


def calculate_track_summary_statistics(land_fraction_df):
    """Calculate summary statistics for each track across all times"""
    print("Calculating track summary statistics...")
    sys.stdout.flush()
    
    if len(land_fraction_df) == 0:
        print("Warning: No data to calculate summary statistics")
        return pd.DataFrame()
    
    summary_stats = []
    
    for (track_id, radius), group in land_fraction_df.groupby(['track_id', 'radius']):
        stats = {
            'track_id': track_id,
            'radius': radius,
            'mean_land_fraction_track': group['mean_land_fraction'].mean(),
            'total_land_fraction_track': group['mean_land_fraction'].sum(),
            'num_time_points': len(group),
            'start_lat': group['meanlat'].iloc[0] if 'meanlat' in group else np.nan,
            'start_lon': group['meanlon'].iloc[0] if 'meanlon' in group else np.nan,
        }
        summary_stats.append(stats)
    
    summary_df = pd.DataFrame(summary_stats)
    print(f"Created summary statistics for {len(summary_df)} track-radius combinations")
    return summary_df


def save_land_fraction_data(land_fraction_df, summary_df, output_dir, output_format='parquet', 
                           model_name=None, zoom_name=None):
    """Save land fraction data to files"""
    os.makedirs(output_dir, exist_ok=True)
    
    if model_name and zoom_name:
        base_filename = f'mcs_land_fractions_{model_name}_zoom{zoom_name}'
    else:
        base_filename = 'mcs_land_fractions'
    
    # Save detailed data
    detailed_path = os.path.join(output_dir, f'{base_filename}_detailed.{output_format}')
    if output_format == 'parquet':
        land_fraction_df.to_parquet(detailed_path, index=False)
    elif output_format == 'csv':
        land_fraction_df.to_csv(detailed_path, index=False)
    elif output_format == 'netcdf':
        land_fraction_df.to_xarray().to_netcdf(detailed_path.replace('.netcdf', '.nc'))
    
    # Save summary data
    summary_path = os.path.join(output_dir, f'{base_filename}_summary.{output_format}')
    if output_format == 'parquet':
        summary_df.to_parquet(summary_path, index=False)
    elif output_format == 'csv':
        summary_df.to_csv(summary_path, index=False)
    elif output_format == 'netcdf':
        summary_df.to_xarray().to_netcdf(summary_path.replace('.netcdf', '.nc'))
    
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
    parser.add_argument('--catalog_model', default="scream_ne120", help='Model name in the catalog')
    parser.add_argument('--catalog_params', default='{"zoom": 8}', help='JSON string of catalog parameters')
    parser.add_argument('--trackfile', required=True, help='Path to MCS track file')
    parser.add_argument('--output_dir', required=True, help='Output directory for results')
    parser.add_argument('--output_format', default='parquet', choices=['parquet', 'csv', 'netcdf'],
                        help='Format to save results')
    
    # Land fraction variable name
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
    parser.add_argument('--radii', default="5,3.5,2", help='Comma-separated list of radii in degrees')
    parser.add_argument('--lat_var', default='meanlat', help='Latitude variable name in tracks')
    parser.add_argument('--lon_var', default='meanlon', help='Longitude variable name in tracks')
    
    args = parser.parse_args()
    
    # Start timing
    start_time = time.time()
    
    print("="*60)
    print("Land Fraction Extraction for MCS Tracks (v2 - optimized)")
    print("="*60)
    print(f"Model: {args.catalog_model}")
    print(f"Catalog params: {args.catalog_params}")
    print(f"Date range: {args.start_date or 'all'} to {args.end_date or 'all'}")
    print(f"Output directory: {args.output_dir}")
    print("="*60)
    sys.stdout.flush()
    
    # Parse RADII
    try:
        RADII = np.array([float(r) for r in args.radii.split(',')])
    except:
        RADII = np.array([5.0, 3.5, 2.0])
    print(f"Using radii: {RADII}")
    sys.stdout.flush()
    
    # Parse catalog parameters
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    # Open catalog and get dataset
    print(f"Opening catalog from {args.catalog_url}")
    sys.stdout.flush()
    cat = intake.open_catalog(args.catalog_url)[args.current_location]
    
    print(f"Loading dataset {args.catalog_model}...")
    sys.stdout.flush()
    ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(egh.attach_coords, signed_lon=True)
    
    # Get HEALPix grid
    print("Computing HEALPix grid...")
    sys.stdout.flush()
    hp_grid = ds[['lat', 'lon']].compute()
    nside = egh.get_nside(hp_grid)
    print(f"Grid: nside={nside}")
    sys.stdout.flush()
    
    # Load land fraction data (keep lazy)
    print(f"Setting up land fraction data ({args.land_fraction_var})...")
    sys.stdout.flush()
    try:
        land_fraction_data = ds[args.land_fraction_var].compute()
    except KeyError:
        print(f"Error: Land fraction variable '{args.land_fraction_var}' not found")
        return
    
    # Load MCS track data 
    sys.stdout.flush()
    mcs_trackstats = xr.open_dataset(args.trackfile)
    
    required_vars = ['meanlon', 'meanlat', 'base_time']
    subset = mcs_trackstats[required_vars].compute()  
    df = subset.to_dataframe().reset_index()
    
    # Filter
    df = df.dropna(subset=[args.lat_var, args.lon_var])
    print(f"After dropping NaN positions: {len(df)} valid track time points")
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
    
    # Apply filters
    filter_conditions = [
        df[args.lat_var].between(min_lat, max_lat),
        df[args.lat_var].notna(),
        df[args.lon_var].notna()
    ]
    
    if args.start_date:
        start_date = pd.Timestamp(args.start_date)
        filter_conditions.append(pd.to_datetime(df['base_time']) >= start_date)
    
    if args.end_date:
        end_date = pd.Timestamp(args.end_date)
        filter_conditions.append(pd.to_datetime(df['base_time']) <= end_date)
    
    if args.min_lon is not None and args.max_lon is not None:
        if args.min_lon > args.max_lon:
            filter_conditions.append((df[args.lon_var] >= args.min_lon) | 
                                    (df[args.lon_var] <= args.max_lon))
        else:
            filter_conditions.append(df[args.lon_var].between(args.min_lon, args.max_lon))
    
    filtered_df = df[np.logical_and.reduce(filter_conditions)].copy()
    filtered_df = filtered_df.reset_index(drop=True)  # Reset index after filtering
    
    print(f"Filtered to {len(filtered_df)} track time points")
    sys.stdout.flush()
    
    # Calculate HEALPix indices
    print("Calculating HEALPix indices...")
    sys.stdout.flush()
    pixel_indices = hp.ang2pix(nside, filtered_df[args.lon_var].values, filtered_df[args.lat_var].values, 
                               nest=True, lonlat=True)
    filtered_df['trigger_idx'] = pixel_indices
    
    # Calculate circular areas 
    all_areas = calculate_circular_areas_sequential(filtered_df, hp_grid, RADII)
    
    # Extract land fraction statistics 
    land_fraction_df = extract_land_fractions_batched(
        all_areas, land_fraction_data, batch_size=500
    )
    
    # Merge track metadata back in 
    print("Merging track metadata with land fraction results...")
    sys.stdout.flush()
    
    # Create metadata lookup from filtered_df
    metadata_df = filtered_df[['tracks', 'times', 'base_time', 'meanlat', 'meanlon']].copy()
    metadata_df = metadata_df.rename(columns={'tracks': 'track_id', 'times': 'time_idx'})
    
    # Merge land fractions with metadata
    land_fraction_df = land_fraction_df.merge(
        metadata_df, 
        on=['track_id', 'time_idx'], 
        how='left'
    )
    
    # Calculate summary statistics
    summary_df = calculate_track_summary_statistics(land_fraction_df)
    
    # Save results
    detailed_path, summary_path = save_land_fraction_data(
        land_fraction_df, summary_df, args.output_dir, args.output_format,
        model_name=args.catalog_model, zoom_name=zoom_level
    )
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Total tracks processed: {len(summary_df['track_id'].unique())}")
    print(f"Total track-time points: {len(land_fraction_df)}")
    print(f"Radii processed: {RADII}")
    
    for radius in RADII:
        radius_data = summary_df[summary_df['radius'] == radius]
        mean_lf = radius_data['mean_land_fraction_track'].mean()
        print(f"  Radius {radius}°: {len(radius_data)} tracks, mean land fraction = {mean_lf:.3f}")
    
    elapsed_time = time.time() - start_time
    print(f"\nExtraction completed in {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    print("="*60)
    
    return detailed_path, summary_path


if __name__ == "__main__":
    main()
