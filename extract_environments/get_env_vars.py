"""
Extract environmental variables around MCS tracks

This script extracts environmental variables (temperature, humidity, etc.) from model output
within circular areas around MCS track positions. It includes:
- Track duration: statistics for each time step of the MCS lifecycle
- Pre-convective period: statistics for 24 hours before track initiation

Key optimizations:
- Uses efficient batched extraction (similar to get_land_fractions.py)
- Minimal track metadata access during extraction (no MultiIndex lookups)
- Metadata merged after extraction using simple join operations

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


def parse_pressure_levels(pressure_str):
    """Parse pressure levels string from bash to list"""
    try:
        return [float(p.strip()) for p in pressure_str.split(',')]
    except:
        return [850, 500, 300]  # Default pressure levels


def detect_pressure_units(pressure_coord):
    """
    Detect whether pressure coordinates are in Pascals or hectopascals.
    
    Parameters:
    -----------
    pressure_coord : xarray.DataArray
        Pressure coordinate from dataset
    
    Returns:
    --------
    str : 'Pa' or 'hPa'
    
    Notes:
    ------
    Heuristic: If the median pressure value is > 2000, assume Pascals (typical range: 100000-10000 Pa)
               If the median pressure value is < 2000, assume hectopascals (typical range: 1000-100 hPa)
    """
    median_pressure = float(np.median(pressure_coord.values))
    
    if median_pressure > 2000:
        units = 'Pa'
        print(f"  Detected pressure units: Pascals (median value: {median_pressure:.1f} Pa)")
    else:
        units = 'hPa'
        print(f"  Detected pressure units: hectopascals (median value: {median_pressure:.1f} hPa)")
    
    sys.stdout.flush()
    return units


def normalize_pressure_levels(pressure_levels_hPa, dataset_pressure_coord):
    """
    Convert user-specified pressure levels (always in hPa) to match dataset units.
    
    Parameters:
    -----------
    pressure_levels_hPa : list
        Pressure levels specified by user in hPa (e.g., [850, 500, 300])
    dataset_pressure_coord : xarray.DataArray
        Pressure coordinate from the dataset
    
    Returns:
    --------
    list : Pressure levels in dataset units
    str : Units detected ('Pa' or 'hPa')
    """
    units = detect_pressure_units(dataset_pressure_coord)
    
    if units == 'Pa':
        # Convert from hPa to Pa
        pressure_levels_dataset = [p * 100 for p in pressure_levels_hPa]
        print(f"  Converting pressure levels from hPa to Pa: {pressure_levels_hPa} hPa → {pressure_levels_dataset} Pa")
    else:
        # Already in hPa
        pressure_levels_dataset = pressure_levels_hPa
        print(f"  Pressure levels: {pressure_levels_hPa} hPa (no conversion needed)")
    
    sys.stdout.flush()
    return pressure_levels_dataset, units


def convert_w_to_omega(ds, pressure_levels_hPa):
    """
    Convert vertical velocity (w) to pressure velocity (omega) using ω = -ρgw
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Dataset containing 'wa' (vertical velocity) and 'ta' (temperature)
    pressure_levels_hPa : list
        List of pressure levels in hPa (will be converted to dataset units automatically)
    
    Returns:
    --------
    xarray.DataArray
        Omega variable (pressure velocity in Pa/s)
    """
    print("Converting vertical velocity (wa) to pressure velocity (omega)...")
    sys.stdout.flush()
    
    # Physical constants
    g = 9.81  # gravitational acceleration (m/s²)
    R = 287.04  # specific gas constant for dry air (J/(kg·K))
    
    # Get variables
    w = ds['wa']  # vertical velocity (m/s)
    T = ds['ta']  # temperature (K)
    
    # Normalize pressure levels to dataset units
    pressure_levels_dataset, pressure_units = normalize_pressure_levels(
        pressure_levels_hPa, w.pressure
    )
    
    # Create omega variable for each pressure level
    omega_levels = []
    
    for i, pressure_hPa in enumerate(pressure_levels_hPa):
        pressure_dataset_units = pressure_levels_dataset[i]
        
        # Select data at this pressure level (using dataset units)
        w_level = w.sel(pressure=pressure_dataset_units, method='nearest')
        T_level = T.sel(pressure=pressure_dataset_units, method='nearest')
        
        # Calculate air density: ρ = P / (R * T)
        # Always use pressure in Pascals for the physics calculation
        if pressure_units == 'hPa':
            pressure_Pa = pressure_hPa * 100
        else:
            pressure_Pa = pressure_dataset_units
        
        density = pressure_Pa / (R * T_level)
        
        # Calculate omega: ω = -ρ * g * w
        omega_level = -density * g * w_level
        
        # Add pressure coordinate (use original hPa value for consistency)
        omega_level = omega_level.expand_dims(pressure=[pressure_hPa])
        omega_levels.append(omega_level)
    
    # Concatenate all pressure levels
    omega_combined = xr.concat(omega_levels, dim='pressure')
    
    # Add proper attributes
    omega_combined.attrs = {
        'long_name': 'Pressure velocity (omega)',
        'units': 'Pa/s',
        'description': 'Pressure velocity calculated from vertical velocity using ω = -ρgw',
        'formula': 'omega = -density * 9.81 * vertical_velocity',
        'pressure_levels_hPa': str(pressure_levels_hPa),
        'source_pressure_units': pressure_units
    }
    
    print(f"Omega conversion complete. Pressure levels: {pressure_levels_hPa} hPa")
    sys.stdout.flush()
    
    # Return only the omega variable, not the entire dataset
    return omega_combined


def convert_omega_to_w(ds, pressure_levels_hPa):
    """
    Convert pressure velocity (omega) to vertical velocity (w) using w = -ω/(ρg)
    
    This is the inverse of the wa-to-omega conversion. Useful when models provide
    omega but you need vertical velocity.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Dataset containing 'omega' (pressure velocity) and 'ta' (temperature)
    pressure_levels_hPa : list
        List of pressure levels in hPa (will be converted to dataset units automatically)
    
    Returns:
    --------
    xarray.DataArray
        Vertical velocity variable (m/s)
    """
    print("Converting pressure velocity (omega) to vertical velocity (wa)...")
    sys.stdout.flush()
    
    # Physical constants
    g = 9.81  # gravitational acceleration (m/s²)
    R = 287.04  # specific gas constant for dry air (J/(kg·K))
    
    # Get variables
    omega = ds['omega']  # pressure velocity (Pa/s)
    T = ds['ta']  # temperature (K)
    
    # Normalize pressure levels to dataset units
    pressure_levels_dataset, pressure_units = normalize_pressure_levels(
        pressure_levels_hPa, omega.pressure
    )
    
    # Create wa variable for each pressure level
    wa_levels = []
    
    for i, pressure_hPa in enumerate(pressure_levels_hPa):
        pressure_dataset_units = pressure_levels_dataset[i]
        
        # Select data at this pressure level (using dataset units)
        omega_level = omega.sel(pressure=pressure_dataset_units, method='nearest')
        T_level = T.sel(pressure=pressure_dataset_units, method='nearest')
        
        # Calculate air density: ρ = P / (R * T)
        # Always use pressure in Pascals for the physics calculation
        if pressure_units == 'hPa':
            pressure_Pa = pressure_hPa * 100
        else:
            pressure_Pa = pressure_dataset_units
        
        density = pressure_Pa / (R * T_level)
        
        # Calculate wa: w = -ω / (ρ * g)
        wa_level = -omega_level / (density * g)
        
        # Add pressure coordinate (use original hPa value for consistency)
        wa_level = wa_level.expand_dims(pressure=[pressure_hPa])
        wa_levels.append(wa_level)
    
    # Concatenate all pressure levels
    wa_combined = xr.concat(wa_levels, dim='pressure')
    
    # Add proper attributes
    wa_combined.attrs = {
        'long_name': 'Vertical velocity (wa)',
        'units': 'm/s',
        'description': 'Vertical velocity calculated from pressure velocity using w = -ω/(ρg)',
        'formula': 'wa = -omega / (density * 9.81)',
        'pressure_levels_hPa': str(pressure_levels_hPa),
        'source_pressure_units': pressure_units
    }
    
    print(f"Vertical velocity conversion complete. Pressure levels: {pressure_levels_hPa} hPa")
    sys.stdout.flush()
    
    # Return only the wa variable, not the entire dataset
    return wa_combined


def load_precomputed_variable(precomputed_dir, variable_name, model_name, zoom_level, 
                               time_res, start_date, end_date):
    """
    Load pre-computed variables from separate files
    
    Parameters:
    -----------
    precomputed_dir : str
        Directory containing pre-computed files
    variable_name : str
        Name of the variable to load
    model_name : str
        Model name (e.g., 'scream_ne120', 'um_glm_n2560_RAL3p3')
    zoom_level : int
        HEALPix zoom level
    time_res : str
        Time resolution (e.g., 'PT3H')
    start_date : pd.Timestamp
        Start date for filtering
    end_date : pd.Timestamp
        End date for filtering
    
    Returns:
    --------
    xarray.DataArray
        Loaded variable data
    """
    print(f"Loading pre-computed variable '{variable_name}' from {precomputed_dir}")
    sys.stdout.flush()
    
    # Generate list of files to load based on date range
    files_to_load = []
    current_date = pd.Timestamp(start_date)
    
    while current_date <= pd.Timestamp(end_date):
        year = current_date.year
        month = current_date.month
        
        # Construct filename pattern
        filename = f"{model_name}_{variable_name}_hp{zoom_level}_{time_res}.{year}{month:02d}.nc"
        filepath = os.path.join(precomputed_dir, filename)
        
        if os.path.exists(filepath):
            files_to_load.append(filepath)
        else:
            print(f"Warning: Pre-computed file not found: {filepath}")
        
        # Move to next month
        current_date = current_date + pd.DateOffset(months=1)
    
    if len(files_to_load) == 0:
        raise FileNotFoundError(f"No pre-computed files found for {variable_name} in {precomputed_dir}")
    
    print(f"Loading {len(files_to_load)} pre-computed file(s)...")
    sys.stdout.flush()

    # Open all files as a single dataset
    ds_combined = xr.open_mfdataset(files_to_load, combine='by_coords')
    ds_combined = ds_combined.pipe(egh.attach_coords, signed_lon=True)
    ds_combined = ds_combined.assign_coords(time=convert_time(ds_combined.time.values))

    # Filter by exact date range
    ds_filtered = ds_combined.sel(time=slice(start_date, end_date))
    
    print(f"Loaded pre-computed variable: {variable_name}, shape: {ds_filtered[variable_name].shape}")
    sys.stdout.flush()
    
    return ds_filtered


def calculate_circular_areas_sequential(mcs_data, hp_grid, radii, progress_freq=50000):
    """
    Calculate circular areas using the proven sequential approach.
    Returns dict with key (track_id, time_idx, radius) -> pixel_array
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


def extract_variable_statistics_batched(all_areas, variable_data, track_times_map,
                                       batch_size=500, variable_name='var', time_batch_size=1000):
    """
    Extract variable statistics for all circular areas using batched processing.
    
    This extracts statistics (mean, median, min, max, std) for the variable within
    each circular area. NO track metadata lookup during extraction.
    
    Parameters:
    -----------
    all_areas : dict
        Dictionary with (track_id, time_idx, radius) -> pixel_array
    variable_data : xarray.DataArray
        The variable to extract (e.g., temperature, humidity)
    track_times_map : dict
        Dictionary mapping (track_id, time_idx) -> base_time (actual timestamp)
    batch_size : int
        Batch size for processing areas
    variable_name : str
        Name of the variable (for progress messages)
    time_batch_size : int
        Number of time steps to load at once (default 500, helps avoid 502 errors for large datasets)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with columns: track_id, time_idx, radius, data_time,
                                mean, median, min, max, std, count, num_valid
    """
    
    # Get all unique pixels and times needed
    all_pixels = set()
    unique_times = set()
    for area_key, pixels in all_areas.items():
        all_pixels.update(pixels)
        track_id, time_idx, radius = area_key
        if (track_id, time_idx) in track_times_map:
            unique_times.add(track_times_map[(track_id, time_idx)])
    
    all_pixels = list(all_pixels)
    unique_times = sorted(list(unique_times))
    
    print(f"Loading {variable_name} data for {len(all_pixels)} pixels and {len(unique_times)} time steps...")
    sys.stdout.flush()
    
    # TIME BATCHING: Load times in batches to avoid 502 Bad Gateway errors
    # This is especially important for IFS with 10,201 hourly timesteps
    num_time_batches = (len(unique_times) + time_batch_size - 1) // time_batch_size
    
    if num_time_batches > 1:
        print(f"Using time batching: {num_time_batches} batches of up to {time_batch_size} time steps")
        sys.stdout.flush()
    
    # Dictionary to store all loaded data: {time -> data_array}
    var_subset_dict = {}
    time_mapping = {}
    
    for time_batch_idx in range(num_time_batches):
        time_start_idx = time_batch_idx * time_batch_size
        time_end_idx = min((time_batch_idx + 1) * time_batch_size, len(unique_times))
        time_batch = unique_times[time_start_idx:time_end_idx]
        
        if num_time_batches > 1:
            print(f"  Loading time batch {time_batch_idx + 1}/{num_time_batches}: {len(time_batch)} times...")
            sys.stdout.flush()
        
        # Add retry logic for each time batch (handles intermittent 502 errors)
        max_retries = 10 #5
        retry_delay = 10 #5
        
        for retry_attempt in range(max_retries):
            try:
                # Load this batch of times
                var_batch = variable_data.sel(cell=all_pixels).sel(time=time_batch, method='nearest').compute()
                
                # Store in dictionary by time
                actual_times_batch = var_batch.time.values
                for i, requested_time in enumerate(time_batch):
                    if i < len(actual_times_batch):
                        actual_time = actual_times_batch[i]
                        time_mapping[requested_time] = actual_time
                        # Store the data array for this time
                        var_subset_dict[actual_time] = var_batch.sel(time=actual_time)
                
                # Success - break out of retry loop
                break
                
            except Exception as e:
                if retry_attempt < max_retries - 1:
                    print(f"    WARNING: Batch {time_batch_idx + 1} failed (attempt {retry_attempt + 1}/{max_retries}): {e}")
                    print(f"    Retrying in {retry_delay} seconds...")
                    sys.stdout.flush()
                    time.sleep(retry_delay)
                else:
                    print(f"    ERROR: Failed to load time batch {time_batch_idx + 1} after {max_retries} attempts: {e}")
                    sys.stdout.flush()
                    # Continue to next batch instead of failing completely
                    continue
    
    if len(var_subset_dict) == 0:
        print(f"ERROR: No variable data loaded successfully")
        return pd.DataFrame()
    
    print(f"Successfully loaded data for {len(var_subset_dict)} time steps")
    print(f"Time mapping created: {len(unique_times)} requested → {len(var_subset_dict)} actual times")
    sys.stdout.flush()
    
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
            
            # Get the actual time for this track position
            if (track_id, time_idx) not in track_times_map:
                continue
            
            track_time = track_times_map[(track_id, time_idx)]
            
            # Map to the actual time that was selected
            if track_time not in time_mapping:
                continue
            
            actual_time = time_mapping[track_time]
            
            # Check if we have data for this time
            if actual_time not in var_subset_dict:
                continue
            
            try:
                # Extract data for THIS specific time using the pre-loaded data
                time_slice = var_subset_dict[actual_time].sel(cell=pixels).values
                valid_values = time_slice[~np.isnan(time_slice)]
                
                if len(valid_values) == 0:
                    continue
                
                # Calculate statistics
                result = {
                    'track_id': int(track_id),
                    'time_idx': int(time_idx),
                    'radius': radius,
                    'data_time': pd.Timestamp(track_time),
                    'mean': float(np.mean(valid_values)),
                    'median': float(np.median(valid_values)),
                    'min': float(np.min(valid_values)),
                    'max': float(np.max(valid_values)),
                    'std': float(np.std(valid_values)),
                    'count': len(pixels),
                    'num_valid': len(valid_values),
                }
                
                results.append(result)
                
            except Exception as e:
                continue
    
    # Convert to DataFrame
    result_df = pd.DataFrame(results)
    
    if len(result_df) > 0:
        result_df = result_df.sort_values(['track_id', 'time_idx', 'radius'])
    
    print(f"Extracted {variable_name} statistics for {len(result_df)} combinations")
    sys.stdout.flush()
    return result_df


def add_preconvective_data(stats_df, preconv_areas, variable_data, track_metadata, 
                           hours_before=24, model_freq='3H', time_batch_size=1000):
    """
    Add pre-convective data (24 hours before track initiation) to the statistics.
    
    For each track, extract data at the FIRST position for time steps going back
    24 hours from the track start time.
    
    Parameters:
    -----------
    stats_df : pd.DataFrame
        Main statistics DataFrame (track duration data)
    preconv_areas : dict
        Dictionary with (track_id, radius) -> pixel_array for first positions
    variable_data : xarray.DataArray
        The variable to extract
    track_metadata : pd.DataFrame
        Metadata with track_id, time_idx, base_time
    hours_before : int
        Hours before initiation to extract (default 24)
    model_freq : str
        Time frequency of data (e.g., '3H' for 3-hourly)
    time_batch_size : int
        Number of time steps to load at once (default 500, helps avoid 502 errors for large datasets)
    
    Returns:
    --------
    pd.DataFrame
        Combined DataFrame with both track duration and pre-convective data
    """
    
    print(f"Adding pre-convective data ({hours_before} hours before initiation)...")
    sys.stdout.flush()
    
    # Check if stats_df is empty
    if len(stats_df) == 0:
        print("Warning: No track duration data to add pre-convective data to")
        return stats_df
    
    # Get first time for each track
    first_times = track_metadata.groupby('track_id').first().reset_index()
    
    # OPTIMIZATION: Collect all pre-convective times and pixels FIRST
    # Then load ALL data at once (like the debug script proved is fastest)
    print(f"Collecting all pre-convective times and pixels for {len(first_times)} tracks...")
    sys.stdout.flush()
    
    preconv_times_map = {}  # (track_id, preconv_time) -> start_time for offset calculation
    all_preconv_times = set()
    all_preconv_pixels = set()
    
    for _, track_info in first_times.iterrows():
        track_id = int(track_info['track_id'])
        start_time = pd.Timestamp(track_info['base_time'])
        
        # Calculate pre-convective time steps
        time_delta = pd.Timedelta(hours=hours_before)
        preconv_start = start_time - time_delta
        
        # Get all time steps in the pre-convective period
        preconv_times = pd.date_range(
            start=preconv_start, 
            end=start_time - pd.Timedelta(model_freq),  # Don't include start_time itself
            freq=model_freq
        )
        
        for preconv_time in preconv_times:
            preconv_times_map[(track_id, pd.Timestamp(preconv_time))] = start_time
            all_preconv_times.add(pd.Timestamp(preconv_time))
    
    # Collect all pixels from all areas
    for pixels in preconv_areas.values():
        all_preconv_pixels.update(pixels)
    
    all_preconv_pixels = list(all_preconv_pixels)
    all_preconv_times = sorted(list(all_preconv_times))
    
    print(f"Loading pre-convective data: {len(all_preconv_pixels)} pixels × {len(all_preconv_times)} times...")
    sys.stdout.flush()
    
    # TIME BATCHING: Load times in batches to avoid 502 Bad Gateway errors
    num_time_batches = (len(all_preconv_times) + time_batch_size - 1) // time_batch_size
    
    if num_time_batches > 1:
        print(f"Using time batching: {num_time_batches} batches of up to {time_batch_size} time steps")
        sys.stdout.flush()
    
    # Dictionary to store all loaded data: {time -> data_array}
    var_preconv_dict = {}
    time_mapping = {}
    
    for time_batch_idx in range(num_time_batches):
        time_start_idx = time_batch_idx * time_batch_size
        time_end_idx = min((time_batch_idx + 1) * time_batch_size, len(all_preconv_times))
        time_batch = all_preconv_times[time_start_idx:time_end_idx]
        
        if num_time_batches > 1:
            print(f"  Loading pre-convective time batch {time_batch_idx + 1}/{num_time_batches}: {len(time_batch)} times...")
            sys.stdout.flush()
        
        # Add retry logic for each time batch (handles intermittent 502 errors)
        max_retries = 10 #3
        retry_delay = 10 #5
        
        for retry_attempt in range(max_retries):
            try:
                # Load this batch of times
                var_batch = variable_data.sel(cell=all_preconv_pixels).sel(time=time_batch, method='nearest').compute()
                
                # Store in dictionary by time
                actual_times_batch = var_batch.time.values
                for i, requested_time in enumerate(time_batch):
                    if i < len(actual_times_batch):
                        actual_time = actual_times_batch[i]
                        time_mapping[requested_time] = actual_time
                        # Store the data array for this time
                        var_preconv_dict[actual_time] = var_batch.sel(time=actual_time)
                
                # Success - break out of retry loop
                break
                
            except Exception as e:
                if retry_attempt < max_retries - 1:
                    print(f"    WARNING: Pre-convective batch {time_batch_idx + 1} failed (attempt {retry_attempt + 1}/{max_retries}): {e}")
                    print(f"    Retrying in {retry_delay} seconds...")
                    sys.stdout.flush()
                    time.sleep(retry_delay)
                else:
                    print(f"    ERROR: Failed to load pre-convective time batch {time_batch_idx + 1} after {max_retries} attempts: {e}")
                    sys.stdout.flush()
                    # Continue to next batch instead of failing completely
                    continue
    
    if len(var_preconv_dict) == 0:
        print(f"ERROR: No pre-convective data loaded successfully")
        return stats_df
    
    print(f"Pre-convective data loaded successfully: {len(var_preconv_dict)} time steps")
    sys.stdout.flush()
    
    # Now extract statistics using the pre-loaded data
    print(f"Extracting pre-convective statistics for {len(first_times)} tracks...")
    sys.stdout.flush()
    
    preconv_results = []
    total_tracks = len(first_times)
    
    # Build a more efficient lookup structure for pre-convective times
    # Group by track_id for faster access
    track_preconv_times = {}
    for (track_id, preconv_time), start_time in preconv_times_map.items():
        if track_id not in track_preconv_times:
            track_preconv_times[track_id] = []
        track_preconv_times[track_id].append((preconv_time, start_time))
    
    for track_idx, track_info in enumerate(first_times.itertuples()):
        # Progress reporting every 10000 tracks
        if track_idx > 0 and track_idx % 10000 == 0:
            print(f"  Processed {track_idx}/{total_tracks} tracks, extracted {len(preconv_results)} data points.")
            sys.stdout.flush()
        
        track_id = int(track_info.track_id)
        first_time_idx = int(track_info.time_idx)
        
        # Skip if no pre-convective times for this track
        if track_id not in track_preconv_times:
            continue
        
        # Process each radius
        for radius in stats_df['radius'].unique():
            area_key = (track_id, radius)
            
            if area_key not in preconv_areas:
                continue
            
            pixels = preconv_areas[area_key]
            
            # Get pre-convective times for this track (already filtered)
            times_for_track = track_preconv_times[track_id]
            
            for preconv_time, start_time in times_for_track:
                if preconv_time not in time_mapping:
                    continue
                
                actual_time = time_mapping[preconv_time]
                
                # Check if we have data for this time
                if actual_time not in var_preconv_dict:
                    continue
                
                try:
                    # Extract from pre-loaded data (FAST!)
                    time_slice = var_preconv_dict[actual_time].sel(cell=pixels).values
                    valid_values = time_slice[~np.isnan(time_slice)]
                    
                    if len(valid_values) == 0:
                        continue
                    
                    # Calculate time offset (negative for pre-convective)
                    time_offset_hours = (preconv_time - start_time).total_seconds() / 3600
                    
                    result = {
                        'track_id': track_id,
                        'time_idx': first_time_idx,
                        'radius': radius,
                        'data_time': preconv_time,
                        'time_offset_hours': time_offset_hours,
                        'mean': float(np.mean(valid_values)),
                        'median': float(np.median(valid_values)),
                        'min': float(np.min(valid_values)),
                        'max': float(np.max(valid_values)),
                        'std': float(np.std(valid_values)),
                        'count': len(pixels),
                        'num_valid': len(valid_values),
                    }
                    
                    preconv_results.append(result)
                    
                except Exception:
                    continue
    
    print(f"  Completed processing all {total_tracks} tracks")
    sys.stdout.flush()
    
    # Combine with main statistics
    preconv_df = pd.DataFrame(preconv_results)
    
    if len(preconv_df) > 0:
        print(f"Added {len(preconv_df)} pre-convective data points")
        
        # Add time_offset_hours to main stats (positive values)
        # Get track start times from metadata
        track_start_times = track_metadata.groupby('track_id')['base_time'].first().to_dict()
        
        # Calculate time offset for main stats
        stats_df['time_offset_hours'] = stats_df.apply(
            lambda row: (row['data_time'] - track_start_times[row['track_id']]).total_seconds() / 3600,
            axis=1
        )
        
        # Select only the columns we need for final output
        main_cols = ['track_id', 'radius', 'data_time', 'time_offset_hours', 
                     'mean', 'median', 'min', 'max', 'std', 'count', 'num_valid']
        preconv_cols = ['track_id', 'radius', 'data_time', 'time_offset_hours',
                       'mean', 'median', 'min', 'max', 'std', 'count', 'num_valid']
        
        # Keep only essential columns
        stats_clean = stats_df[main_cols].copy()
        preconv_clean = preconv_df[preconv_cols].copy()
        
        # Combine
        combined_df = pd.concat([stats_clean, preconv_clean], ignore_index=True)
        combined_df = combined_df.sort_values(['track_id', 'time_offset_hours', 'radius'])
        
        return combined_df
    else:
        print("Warning: No pre-convective data extracted")
        
        # Still need to add time_offset_hours to stats_df
        track_start_times = track_metadata.groupby('track_id')['base_time'].first().to_dict()
        stats_df['time_offset_hours'] = stats_df.apply(
            lambda row: (row['data_time'] - track_start_times[row['track_id']]).total_seconds() / 3600,
            axis=1
        )
        
        # Select only essential columns
        final_cols = ['track_id', 'radius', 'data_time', 'time_offset_hours', 
                     'mean', 'median', 'min', 'max', 'std', 'count', 'num_valid']
        return stats_df[final_cols].copy()


def align_track_times_to_dataset(df, dataset_times, time_column='base_time'):
    """
    Align track timestamps to the nearest dataset times.
    
    This is crucial for resampled datasets (e.g., IFS 1H → 3H):
    - Without alignment: tracks keep original timestamps → 10,199 unique times
    - With alignment: tracks snap to dataset times → 3,401 unique times
    - Results in ~3× fewer time batches and ~3× faster extraction
    
    Parameters:
    -----------
    df : pd.DataFrame
        Track dataframe with time column
    dataset_times : array-like
        Available times in the dataset (e.g., from ds.time.values)
    time_column : str
        Name of time column in df (default: 'base_time')
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with aligned timestamps
    """
    print(f"Aligning track times to dataset times...")
    print(f"  Dataset has {len(dataset_times)} time steps")
    sys.stdout.flush()
    
    # Convert to pandas datetime for easier manipulation
    dataset_times_pd = pd.to_datetime(dataset_times)
    track_times_pd = pd.to_datetime(df[time_column])
    
    # For each track time, find nearest dataset time
    aligned_times = []
    for track_time in track_times_pd:
        # Find nearest dataset time
        time_diffs = np.abs(dataset_times_pd - track_time)
        nearest_idx = time_diffs.argmin()
        aligned_times.append(dataset_times_pd[nearest_idx])
    
    # Create new dataframe with aligned times
    df_aligned = df.copy()
    df_aligned[time_column] = aligned_times
    
    # Report statistics
    original_unique = len(track_times_pd.unique())
    aligned_unique = len(pd.Series(aligned_times).unique())
    reduction = (1 - aligned_unique / original_unique) * 100
    
    print(f"  Original unique times: {original_unique}")
    print(f"  Aligned unique times: {aligned_unique}")
    print(f"  Reduction: {reduction:.1f}%")
    sys.stdout.flush()
    
    return df_aligned


def load_land_fraction_summary(land_fraction_file, land_threshold=None):
    """
    Load land fraction summary file and optionally filter by land fraction threshold.
    
    Parameters:
    -----------
    land_fraction_file : str
        Path to land fraction summary parquet file
    land_threshold : float, optional
        If provided, only keep tracks with total_land_fraction_track < threshold
    
    Returns:
    --------
    tuple : (track_ids, land_fraction_df)
        Set of track IDs to process and full land fraction DataFrame
    """
    print(f"Loading land fraction summary from {land_fraction_file}")
    sys.stdout.flush()
    
    try:
        lf_df = pd.read_parquet(land_fraction_file)
        print(f"Loaded land fraction data for {len(lf_df)} track-radius combinations")
        
        if land_threshold is not None:
            # Filter by land fraction threshold
            ocean_mask = lf_df['total_land_fraction_track'] < land_threshold
            lf_df = lf_df[ocean_mask]
            print(f"After land fraction filtering (< {land_threshold}): {len(lf_df)} combinations")
        
        # Get unique track IDs
        track_ids = set(lf_df['track_id'].unique())
        print(f"Processing {len(track_ids)} unique tracks")
        
        return track_ids, lf_df
        
    except Exception as e:
        print(f"ERROR: Failed to load land fraction file: {e}")
        raise


def save_results(result_df, output_path, variable_name, pressure_suffix=''):
    """Save results to parquet file
    
    Parameters:
    -----------
    result_df : pd.DataFrame
        Results to save
    output_path : str
        Base output path (without extension)
    variable_name : str
        Variable name
    pressure_suffix : str, optional
        Suffix to add for pressure level info (e.g., '_850hPa', '_avg850-500-300hPa')
    """
    output_file = f"{output_path}_{variable_name}{pressure_suffix}.parquet"
    result_df.to_parquet(output_file, index=False)
    print(f"Results saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Extract environmental variables around MCS tracks.'
    )
    
    # Input/output options
    parser.add_argument('--catalog_url', 
                        default="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml",
                        help='URL of the intake catalog')
    parser.add_argument('--current_location', default="NERSC", 
                        help='Current location in catalog')
    parser.add_argument('--catalog_model', default="scream_ne120", 
                        help='Model name in the catalog')
    parser.add_argument('--catalog_params', default='{"zoom": 8}', 
                        help='JSON string of catalog parameters')
    parser.add_argument('--trackfile', required=True, 
                        help='Path to MCS track file')
    parser.add_argument('--output_dir', required=True, 
                        help='Output directory for results')
    parser.add_argument('--variable', '--variables', nargs='+', required=True, 
                        dest='variables',
                        help='Variable(s) to extract from dataset (can specify multiple)')
    
    # Land fraction filtering
    parser.add_argument('--land_fraction_file', default=None,
                        help='Path to land fraction summary file (parquet)')
    parser.add_argument('--land_threshold', type=float, default=None,
                        help='Land fraction threshold (only process tracks with LF < threshold)')
    
    # Date filtering options - NOW SUPPORTS MULTIPLE RANGES
    parser.add_argument('--start_date', help='Start date for filtering (YYYY-MM-DD)')
    parser.add_argument('--end_date', help='End date for filtering (YYYY-MM-DD)')
    parser.add_argument('--date_ranges', nargs='+', 
                        help='Multiple date ranges as: "YYYY-MM-DD YYYY-MM-DD" "YYYY-MM-DD YYYY-MM-DD" ...')
    
    # Spatial filtering options
    parser.add_argument('--min_lon', type=float, default=None, help='Minimum longitude')
    parser.add_argument('--max_lon', type=float, default=None, help='Maximum longitude')
    parser.add_argument('--min_lat', type=float, default=None, help='Minimum latitude')
    parser.add_argument('--max_lat', type=float, default=None, help='Maximum latitude')
    
    # Processing options
    parser.add_argument('--radii', default="5,3.5,2", 
                        help='Comma-separated list of radii in degrees')
    parser.add_argument('--lat_var', default='meanlat', 
                        help='Latitude variable name in tracks')
    parser.add_argument('--lon_var', default='meanlon', 
                        help='Longitude variable name in tracks')
    parser.add_argument('--hours_before_init', type=int, default=24,
                        help='Hours before initiation to extract (pre-convective)')
    parser.add_argument('--batch_size', type=int, default=500,
                        help='Batch size for processing')
    
    # 3D variable options
    parser.add_argument('--pressure_levels', default=None, 
                        help='Comma-separated list of pressure levels in hPa (e.g., "850,500,300")')
    parser.add_argument('--process_all_levels', action='store_true',
                        help='Process all pressure levels separately (creates one file per level)')
    
    # Pre-computed variable options
    parser.add_argument('--precomputed_dir', default=None,
                        help='Directory containing pre-computed variables')
    parser.add_argument('--time_res', default='PT3H',
                        help='Time resolution of precomputed files (e.g., PT3H)')
    
    # Vertical velocity conversion
    parser.add_argument('--convert_wa_to_omega', action='store_true',
                        help='Convert vertical velocity (wa) to pressure velocity (omega)')
    parser.add_argument('--convert_omega_to_wa', action='store_true',
                        help='Convert pressure velocity (omega) to vertical velocity (wa)')
    
    # Model time frequency
    parser.add_argument('--model_time_freq', default=None,
                        help='Model output time frequency (e.g., "1H", "3H", "6H") - used to subsample track time steps')
    
    # Time batching parameter (for large datasets like IFS)
    parser.add_argument('--time_batch_size', type=int, default=1000,
                        help='Number of time steps to load at once (default 1000). Reduce to 500 for large datasets like IFS to avoid 502 errors')
    
    args = parser.parse_args()
    
    # Determine date ranges to process
    if args.date_ranges:
        # Multiple date ranges provided
        date_ranges = []
        for dr in args.date_ranges:
            parts = dr.split()
            if len(parts) == 2:
                date_ranges.append((parts[0], parts[1]))
        print(f"Processing {len(date_ranges)} date ranges")
    elif args.start_date and args.end_date:
        # Single date range
        date_ranges = [(args.start_date, args.end_date)]
    else:
        # No date filtering
        date_ranges = [(None, None)]
    
    # Define subsampling function
    def subsample_tracks_by_frequency(df, model_freq):
        """
        Subsample track time steps to match model output frequency.
        
        Parameters:
        -----------
        df : pandas.DataFrame
            Track dataframe with 'tracks', 'times', and 'base_time' columns
        model_freq : str
            Model output frequency (e.g., '1H', '3H', '6H')
        
        Returns:
        --------
        pandas.DataFrame
            Filtered dataframe with only time steps aligned to model frequency
        """
        # import pandas as pd
        
        print(f"Subsampling tracks to model frequency: {model_freq}")
        original_count = len(df)
        
        # Convert frequency string to timedelta
        freq_td = pd.Timedelta(model_freq)
        
        # Group by track and filter
        filtered_rows = []
        for track_id, track_group in df.groupby('tracks'):
            # Sort by time
            track_group = track_group.sort_values('times')
            
            # Get base times
            base_times = pd.to_datetime(track_group['base_time'].values)
            
            # Find the first timestamp for this track
            first_time = base_times.min()
            
            # Create mask for times that align with model frequency
            time_diffs = base_times - first_time
            # Keep times where the difference is a multiple of model frequency
            aligned_mask = (time_diffs % freq_td) == pd.Timedelta(0)
            
            filtered_rows.append(track_group[aligned_mask])
        
        result_df = pd.concat(filtered_rows, ignore_index=True)
        new_count = len(result_df)
        reduction = (1 - new_count/original_count) * 100
        
        print(f"Subsampled from {original_count} to {new_count} time points ({reduction:.1f}% reduction)")
        
        return result_df
    
    # Start timing
    total_start_time = time.time()
    
    print("="*60)
    print(f"Environmental Variable Extraction")
    print("="*60)
    print(f"Model: {args.catalog_model}")
    print(f"Output directory: {args.output_dir}")
    print(f"Variables: {', '.join(args.variables)}")
    print(f"Number of date ranges: {len(date_ranges)}")
    print("="*60)
    sys.stdout.flush()
    
    # Parse radii
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
    
    # Load land fraction data if provided
    tracks_to_process = None
    land_fraction_df = None
    
    if args.land_fraction_file:
        tracks_to_process, land_fraction_df = load_land_fraction_summary(
            args.land_fraction_file, 
            args.land_threshold
        )
    
    # Open catalog and get dataset
    print(f"Opening catalog from {args.catalog_url}")
    sys.stdout.flush()
    cat = intake.open_catalog(args.catalog_url)[args.current_location]
    
    print(f"Loading dataset {args.catalog_model}...")
    sys.stdout.flush()
    
    # Add retry logic for dataset opening (handles intermittent 502 errors)
    max_retries = 10
    retry_delay = 10  # seconds
    
    for attempt in range(max_retries):
        try:
            ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(
                egh.attach_coords, signed_lon=True
            )
            ds = ds.assign_coords(time=convert_time(ds.time.values))
            # Resample IMMEDIATELY for IFS
            if args.catalog_model.startswith('ifs'):
                print(f"Resampling IFS data from hourly to {args.model_time_freq}...")
                ds = ds.resample(time=args.model_time_freq).first()
                print(f"After resampling: {len(ds.time)} time steps")

            print(f"Dataset loaded successfully")
            sys.stdout.flush()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"WARNING: Failed to load dataset (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                sys.stdout.flush()
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"ERROR: Failed to load dataset after {max_retries} attempts: {e}")
                sys.stdout.flush()
                raise
    
    # ===== FIX FOR IFS MODEL: Rename dimensions and variables =====
    # IFS has both 'value' and 'cell' dimensions, but variables use 'value'
    # Also, IFS uses 'level' instead of 'pressure' for vertical coordinate
    if 'value' in ds.dims and 'cell' in ds.dims:
        print("Detected IFS model: Applying dimension and variable name fixes...")
        sys.stdout.flush()
        
        # 1. Swap 'value' dimension to 'cell'
        # IFS has both 'value' (no coordinate) and 'cell' (with coordinate) dimensions
        # Variables are indexed by 'value', but we need them indexed by 'cell'
        # Strategy: save cell values, drop old cell dimension, rename value→cell, reassign coordinate
        cell_values = ds.coords['cell'].values
        ds = ds.drop_dims('cell')
        ds = ds.rename({'value': 'cell'})
        ds = ds.assign_coords({'cell': cell_values})
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        # ds = ds.resample(time="3H").first()
        print("Swapped 'value' → 'cell' dimension")
        
        # 2. Rename 'level' to 'pressure' if it exists
        if 'level' in ds.dims:
            ds = ds.rename({'level': 'pressure'})
            print("Renamed 'level' → 'pressure' dimension")
        
        # 3. Rename IFS variable names to standard names (only if they exist)
        var_name_mapping = {
            't': 'ta',      # temperature
            'w': 'omega',      # vertical velocity
            'q': 'hus',    # specific humidity
            'r': 'hur',     # relative humidity
            '2t': 'tas'     # 2m temperature
        }
        
        vars_to_rename = {}
        for old_name, new_name in var_name_mapping.items():
            if old_name in ds.data_vars or old_name in ds.coords:
                vars_to_rename[old_name] = new_name
        
        if vars_to_rename:
            ds = ds.rename(vars_to_rename)
            print(f"Renamed variables: {vars_to_rename}")
        
        print("IFS model fixes complete")
        sys.stdout.flush()
    
    # ===== FIX FOR NICAM MODEL: Rename dimensions and variables =====
    # NICAM uses 'lev' instead of 'pressure' for vertical coordinate
    if 'lev' in ds.dims:
        print("Detected NICAM model: Renaming 'lev' → 'pressure' dimension...")
        sys.stdout.flush()
        ds = ds.rename({'lev': 'pressure'})
        print("NICAM model fix complete")
        sys.stdout.flush()
    
    # ===== FIX FOR SCREAM MODEL: Rename dimensions and variables =====
    # SCREAM uses 'level' instead of 'pressure' for vertical coordinate and pressure values are in 'lev' coordinate
    if 'level' in ds.dims:
        print("Detected SCREAM model: Renaming 'level' → 'pressure' dimension...")
        sys.stdout.flush()
        ds = ds.rename({'level': 'pressure'})
        ds = ds.assign_coords(pressure=('pressure', ds.lev.values))
        ds = ds.drop_vars('lev')
        print("SCREAM model fix complete")
        sys.stdout.flush()
    
    # Get HEALPix grid
    print("Computing HEALPix grid...")
    sys.stdout.flush()
    hp_grid = ds[['lat', 'lon']].compute()
    nside = egh.get_nside(hp_grid)
    print(f"Grid: nside={nside}")
    sys.stdout.flush()
    
    # =================================================================
    # LOAD MCS TRACK DATA ONCE (for all variables and date ranges!)
    # =================================================================
    print(f"Loading MCS track data from {args.trackfile}")
    sys.stdout.flush()
    mcs_trackstats = xr.open_dataset(args.trackfile)
    
    # ONLY load essential variables
    required_vars = ['meanlon', 'meanlat', 'base_time']
    subset = mcs_trackstats[required_vars].compute()
    df_all = subset.to_dataframe().reset_index()
    print(f"Loaded {len(df_all)} total track-time points")
    
    # Filter by tracks from land fraction file if provided
    if tracks_to_process is not None:
        df_all = df_all[df_all['tracks'].isin(tracks_to_process)]
        print(f"Filtered to {len(df_all)} track-time points from land fraction file")
    
    # Apply spatial filtering (not temporal - that's per date range)
    df_all = df_all.dropna(subset=[args.lat_var, args.lon_var])
    print(f"After dropping NaN positions: {len(df_all)} valid track time points")
    
    # Set spatial bounds
    if args.min_lat is None:
        min_lat = -90 + RADII.max()
    else:
        min_lat = args.min_lat
    
    if args.max_lat is None:
        max_lat = 90 - RADII.max()
    else:
        max_lat = args.max_lat
    
    # Apply spatial filters only (temporal filtering happens per date range)
    spatial_filter_conditions = [
        df_all[args.lat_var].between(min_lat, max_lat),
        df_all[args.lat_var].notna(),
        df_all[args.lon_var].notna()
    ]
    
    if args.min_lon is not None and args.max_lon is not None:
        if args.min_lon > args.max_lon:
            spatial_filter_conditions.append((df_all[args.lon_var] >= args.min_lon) | 
                                            (df_all[args.lon_var] <= args.max_lon))
        else:
            spatial_filter_conditions.append(df_all[args.lon_var].between(args.min_lon, args.max_lon))
    
    df_spatial_filtered = df_all[np.logical_and.reduce(spatial_filter_conditions)].copy()
    df_spatial_filtered = df_spatial_filtered.reset_index(drop=True)
    print(f"After spatial filtering: {len(df_spatial_filtered)} track time points")
    print(f"This dataset will be reused for all {len(args.variables)} variable(s) and {len(date_ranges)} date range(s)")
    sys.stdout.flush()
    
    # Calculate HEALPix indices ONCE
    print("Calculating HEALPix indices...")
    sys.stdout.flush()
    pixel_indices = hp.ang2pix(
        nside, 
        df_spatial_filtered[args.lon_var].values, 
        df_spatial_filtered[args.lat_var].values, 
        nest=True, 
        lonlat=True
    )
    df_spatial_filtered['trigger_idx'] = pixel_indices
    
    # NOTE: Time alignment will happen AFTER track subsampling (inside date range loop)
    # This is critical because subsampling needs original timestamps to work correctly
    
    # Parse pressure levels if provided
    pressure_levels = None
    if args.pressure_levels:
        pressure_levels = parse_pressure_levels(args.pressure_levels)
        print(f"Using pressure levels: {pressure_levels} hPa")
        sys.stdout.flush()
    
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
        # HANDLE DIFFERENT VARIABLE SOURCES
        # =================================================================
        
        # Option 1: Pre-computed variable from separate files
        if args.precomputed_dir:
            print(f"Loading pre-computed variable from {args.precomputed_dir}")
            sys.stdout.flush()
            
            # Need to load per date range since file names depend on dates
            variable_data = None  # Will be loaded per date range
            use_precomputed = True
        
        # Option 2: Vertical velocity conversion (wa -> omega)
        elif variable_name == 'wa' and args.convert_wa_to_omega:
            print("Converting vertical velocity (wa) to pressure velocity (omega)...")
            sys.stdout.flush()
            
            if pressure_levels is None:
                print("ERROR: --pressure_levels required for wa to omega conversion")
                continue
            
            # Check if required variables exist
            if 'wa' not in ds or 'ta' not in ds:
                print(f"ERROR: Variables 'wa' and 'ta' required for omega conversion")
                continue
            
            # Convert wa to omega (returns only omega variable, not full dataset)
            variable_data = convert_w_to_omega(ds, pressure_levels)
            variable_name = 'omega'  # Change variable name for output
            print(f"Variable data ready (omega)")
            use_precomputed = False
            
            # Set pressure suffix for output filename
            is_3d_variable = True
            if len(pressure_levels) == 1:
                pressure_suffix = f"_{int(pressure_levels[0])}hPa"
            else:
                levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                pressure_suffix = f"_avg{levels_str}hPa"
        
        # Option 2b: Inverse conversion (omega -> wa)
        elif variable_name == 'omega' and args.convert_omega_to_wa:
            print("Converting pressure velocity (omega) to vertical velocity (wa)...")
            sys.stdout.flush()
            
            if pressure_levels is None:
                print("ERROR: --pressure_levels required for omega to wa conversion")
                continue
            
            # Check if required variables exist
            if 'omega' not in ds or 'ta' not in ds:
                print(f"ERROR: Variables 'omega' and 'ta' required for wa conversion")
                continue
            
            # Convert omega to wa (returns only wa variable, not full dataset)
            variable_data = convert_omega_to_w(ds, pressure_levels)
            variable_name = 'wa'  # Change variable name for output
            print(f"Variable data ready (wa)")
            use_precomputed = False
            
            # Set pressure suffix for output filename
            is_3d_variable = True
            if len(pressure_levels) == 1:
                pressure_suffix = f"_{int(pressure_levels[0])}hPa"
            else:
                levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                pressure_suffix = f"_avg{levels_str}hPa"
        
        # Option 3: Standard variable from catalog
        else:
            print(f"Setting up variable data ({variable_name})...")
            sys.stdout.flush()
            
            try:
                variable_data = ds[variable_name]
                
                # Check if it's a 3D variable with pressure levels
                if 'pressure' in variable_data.dims and pressure_levels is not None:
                    is_3d_variable = True
                    
                    if args.process_all_levels:
                        print(f"3D variable detected with pressure dimension")
                        print(f"Will process each pressure level separately")
                        # Pressure suffix will be set per level in the loop below
                    else:
                        print(f"3D variable detected with pressure dimension")
                        print(f"Requested pressure levels: {pressure_levels} hPa")
                        
                        # Normalize pressure levels to match dataset units
                        pressure_levels_dataset, pressure_units = normalize_pressure_levels(
                            pressure_levels, variable_data.pressure
                        )
                        
                        # SELECT PRESSURE LEVEL(S) IMMEDIATELY
                        # This reduces from 3D (cell, time, pressure) to 2D (cell, time)
                        # Making all subsequent operations much faster
                        if len(pressure_levels_dataset) == 1:
                            # Single level - just select it
                            variable_data = variable_data.sel(
                                pressure=pressure_levels_dataset[0], method='nearest'
                            )
                            pressure_suffix = f"_{int(pressure_levels[0])}hPa"
                            print(f"Selected single pressure level: {pressure_levels[0]} hPa")
                        else:
                            # Multiple levels - select then average
                            variable_data = variable_data.sel(
                                pressure=pressure_levels_dataset, method='nearest'
                            ).mean(dim='pressure')
                            levels_str = '-'.join([str(int(p)) for p in pressure_levels])
                            pressure_suffix = f"_avg{levels_str}hPa"
                            print(f"Selected and averaged pressure levels: {pressure_levels} hPa")
                        
                        print(f"Variable is now 2D (cell, time) - ready for efficient loading")
                
                print(f"Variable data ready")
                use_precomputed = False
                
            except KeyError:
                print(f"ERROR: Variable '{variable_name}' not found in dataset")
                print(f"Skipping {variable_name}")
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
            
            # Load pre-computed variable for this date range if needed
            if use_precomputed and start_date_str and end_date_str:
                try:
                    ds_precomp = load_precomputed_variable(
                        args.precomputed_dir,
                        original_variable,
                        args.catalog_model,
                        zoom_level,
                        args.time_res,
                        start_date_str,
                        end_date_str
                    )
                    variable_data = ds_precomp[original_variable]
                    print(f"Pre-computed variable data ready")
                except Exception as e:
                    print(f"ERROR: Failed to load pre-computed variable: {e}")
                    continue
            
            # Filter by date range
            if start_date_str and end_date_str:
                start_date = pd.Timestamp(start_date_str)
                end_date = pd.Timestamp(end_date_str)
                date_filter = (
                    (pd.to_datetime(df_spatial_filtered['base_time']) >= start_date) & 
                    (pd.to_datetime(df_spatial_filtered['base_time']) <= end_date)
                )
                filtered_df = df_spatial_filtered[date_filter].copy()
                print(f"Filtered to {len(filtered_df)} track time points for this date range")
            else:
                filtered_df = df_spatial_filtered.copy()
                print(f"Processing all {len(filtered_df)} track time points (no date filter)")
            
            if len(filtered_df) == 0:
                print(f"WARNING: No tracks in date range {start_date_str} to {end_date_str}, skipping")
                continue
            
            # Subsample tracks to model frequency if specified
            if args.model_time_freq and args.model_time_freq not in ['1H', '1h']:
                filtered_df = subsample_tracks_by_frequency(filtered_df, args.model_time_freq)
                if len(filtered_df) == 0:
                    print(f"WARNING: No tracks remain after subsampling, skipping")
                    continue
            
            # CRITICAL: Align track times to dataset times AFTER subsampling
            # This must happen after subsampling because subsampling needs original timestamps
            # Time alignment dramatically reduces unique times (e.g., 10,199 → 3,401 for IFS)
            print("\nAligning track times to dataset times...")
            sys.stdout.flush()
            filtered_df = align_track_times_to_dataset(filtered_df, ds.time.values, 'base_time')
            
            sys.stdout.flush()
            
            # Calculate circular areas for this date range
            all_areas = calculate_circular_areas_sequential(filtered_df, hp_grid, RADII)
            
            # Extract pre-convective areas from all_areas (first time_idx per track)
            # No need to recalculate - they're already in all_areas!
            print("Extracting pre-convective areas (first time step per track)...")
            sys.stdout.flush()
            first_time_idx = filtered_df.groupby('tracks')['times'].first().to_dict()
            preconv_areas = {}
            for (track_id, time_idx, radius), pixels in all_areas.items():
                if time_idx == first_time_idx.get(track_id):
                    preconv_areas[(track_id, radius)] = pixels
            print(f"Extracted pre-convective areas for {len(set(k[0] for k in preconv_areas.keys()))} tracks")
            
            # Create time mapping
            print("Creating track time mapping...")
            sys.stdout.flush()
            track_times_map = {}
            for _, row in filtered_df.iterrows():
                track_id = int(row['tracks'])
                time_idx = int(row['times'])
                track_times_map[(track_id, time_idx)] = pd.Timestamp(row['base_time'])
            
            # Extract variable statistics
            print(f"Extracting {variable_name} statistics for track duration...")
            sys.stdout.flush()
            
            stats_df = extract_variable_statistics_batched(
                all_areas, 
                variable_data, 
                track_times_map,
                batch_size=args.batch_size,
                variable_name=variable_name,
                time_batch_size=args.time_batch_size
            )
            
            if len(stats_df) == 0:
                print(f"WARNING: No data extracted for date range {start_date_str} to {end_date_str}")
                continue
            
            # Add pre-convective data (this also adds time_offset_hours)
            if args.hours_before_init > 0:
                track_metadata = filtered_df[['tracks', 'times', 'base_time']].copy()
                track_metadata = track_metadata.rename(
                    columns={'tracks': 'track_id', 'times': 'time_idx'}
                )
                
                stats_df = add_preconvective_data(
                    stats_df, 
                    preconv_areas, 
                    variable_data,
                    track_metadata,
                    hours_before=args.hours_before_init,
                    model_freq=args.model_time_freq,
                    time_batch_size=args.time_batch_size
                )
            else:
                # If no pre-convective data, still need to add time_offset_hours
                track_metadata = filtered_df[['tracks', 'times', 'base_time']].copy()
                track_metadata = track_metadata.rename(
                    columns={'tracks': 'track_id', 'times': 'time_idx'}
                )
                track_start_times = track_metadata.groupby('track_id')['base_time'].first().to_dict()
                stats_df['time_offset_hours'] = stats_df.apply(
                    lambda row: (row['data_time'] - track_start_times[row['track_id']]).total_seconds() / 3600,
                    axis=1
                )
                # Keep only essential columns
                final_cols = ['track_id', 'radius', 'data_time', 'time_offset_hours', 
                             'mean', 'median', 'min', 'max', 'std', 'count', 'num_valid']
                stats_df = stats_df[final_cols].copy()
            
            # Save results for this date range in variable-specific subdirectory
            var_output_dir = os.path.join(args.output_dir, variable_name)
            os.makedirs(var_output_dir, exist_ok=True)
            start_str = start_date_str.replace('-', '') if start_date_str else "unknown"
            end_str = end_date_str.replace('-', '') if end_date_str else "unknown"
            output_path = os.path.join(
                var_output_dir,
                f"mcs_env_{variable_name}_{start_str}_{end_str}"
            )
            
            # Save results with pressure level info if applicable
            output_file = save_results(stats_df, output_path, variable_name, pressure_suffix)
            
            # Print summary for this date range
            print("\n" + "="*60)
            print(f"SUMMARY STATISTICS - {variable_name} - Date range {range_idx + 1}/{len(date_ranges)}")
            print("="*60)
            print(f"Total tracks processed: {stats_df['track_id'].nunique()}")
            print(f"Total data points: {len(stats_df)}")
            print(f"Radii processed: {RADII}")
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
        print(f"Average per variable: {total_elapsed_time/len(args.variables):.2f} seconds")
    print("="*60)


if __name__ == "__main__":
    main()
