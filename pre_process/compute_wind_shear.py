"""
Compute Wind Shear (Low-Shear and Deep-Shear) from HEALPix Zarr data

This script computes:
- Low-Shear: 400 hPa - 1000 hPa (magnitude and direction)
- Deep-Shear: 850 hPa - 100 hPa (magnitude and direction)

Handles different models (IFS, SCREAM, NICAM, etc.) with varying:
- Dimension names (value/cell, level/lev/pressure)
- Variable names (t/ta, q/hus, u/ua, v/va)
- Pressure units (Pa vs hPa)

Author: Laura Paccini
Last updated: October 2025
"""

import os
import json
import datetime
import numpy as np
import xarray as xr
import intake
import easygems.healpix as egh
import sys
import argparse
import time

# =================== Utility Functions =======================

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return np.array([np.datetime64(datetime.datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])
    return time_array


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
    tuple : (pressure_levels_dataset, units)
        Pressure levels in dataset units and the detected units
    """
    units = detect_pressure_units(dataset_pressure_coord)
    
    if units == 'Pa':
        # Convert from hPa to Pa
        pressure_levels_dataset = [p * 100 for p in pressure_levels_hPa]
        print(f"  Converted pressure levels: {pressure_levels_hPa} hPa → {pressure_levels_dataset} Pa")
    else:
        # Already in hPa
        pressure_levels_dataset = pressure_levels_hPa
        print(f"  Pressure levels: {pressure_levels_hPa} hPa (no conversion needed)")
    
    sys.stdout.flush()
    return pressure_levels_dataset, units


def apply_model_fixes(ds, model_name):
    """
    Apply model-specific fixes for dimension and variable names.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Input dataset
    model_name : str
        Model name (e.g., 'ifs', 'scream', 'nicam')
    
    Returns:
    --------
    xarray.Dataset
        Fixed dataset with standardized names
    """
    print(f"\nApplying fixes for model: {model_name}")
    sys.stdout.flush()
    
    # ===== FIX FOR IFS MODEL =====
    if 'value' in ds.dims and 'cell' in ds.dims:
        print("  Detected IFS model: Applying dimension and variable name fixes...")
        sys.stdout.flush()
        
        # 1. Swap 'value' dimension to 'cell'
        cell_values = ds.coords['cell'].values
        ds = ds.drop_dims('cell')
        ds = ds.rename({'value': 'cell'})
        ds = ds.assign_coords({'cell': cell_values})
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        print("    Swapped 'value' → 'cell' dimension")
        
        # 2. Rename 'level' to 'pressure' if it exists
        if 'level' in ds.dims:
            ds = ds.rename({'level': 'pressure'})
            print("    Renamed 'level' → 'pressure' dimension")
        
        # 3. Rename IFS variable names to standard names
        var_name_mapping = {
            't': 'ta',      # temperature
            'w': 'omega',   # vertical velocity (pressure velocity)
            'q': 'hus',     # specific humidity
            'r': 'hur',     # relative humidity
            'u': 'ua',      # zonal wind
            'v': 'va',      # meridional wind
            '2t': 'tas',    # 2m temperature
            '2d': 'tdas',   # 2m dew point temperature
            'sp': 'ps',     # surface pressure

        }
        
        vars_to_rename = {}
        for old_name, new_name in var_name_mapping.items():
            if old_name in ds.data_vars or old_name in ds.coords:
                vars_to_rename[old_name] = new_name
        
        if vars_to_rename:
            ds = ds.rename(vars_to_rename)
            print(f"    Renamed variables: {vars_to_rename}")
        
        print("  IFS model fixes complete")
        sys.stdout.flush()
    
    # ===== FIX FOR PRESSURE DIMENSION NAMES =====
    # Standardize pressure dimension to 'pressure'
    if 'lev' in ds.dims:
        ds = ds.rename({'lev': 'pressure'})
        print("  Renamed dimension: 'lev' → 'pressure'")
        sys.stdout.flush()
    
    # Some models use 'level' instead of 'pressure'
    if 'level' in ds.dims:
        # For SCREAM: 'level' dimension needs coordinate from 'lev' variable
        if 'scream' in model_name.lower():
            ds = ds.rename({'level': 'pressure'})
            print("  Renamed dimension: 'level' → 'pressure' (SCREAM)")
            if 'lev' in ds.data_vars or 'lev' in ds.coords:
                ds = ds.assign_coords(pressure=('pressure', ds.lev.values))
                ds = ds.drop_vars('lev')
                print("  Assigned pressure coordinate from 'lev' variable")
            sys.stdout.flush()
        # For ERA5 and other models: 'level' is already the pressure coordinate
        else:
            ds = ds.rename({'level': 'pressure'})
            print("  Renamed dimension: 'level' → 'pressure'")
            sys.stdout.flush()
    
    return ds


def compute_wind_shear(ua_upper, va_upper, ua_lower, va_lower):
    """
    Compute wind shear magnitude and direction.
    
    Shear = Upper_level_wind - Lower_level_wind
    
    Parameters:
    -----------
    ua_upper, va_upper : xarray.DataArray
        Zonal and meridional wind components at upper level
    ua_lower, va_lower : xarray.DataArray
        Zonal and meridional wind components at lower level
    
    Returns:
    --------
    tuple : (shear_magnitude, shear_direction)
        Shear magnitude (m/s) and direction (degrees, 0-360°, meteorological convention)
    """
    # Compute shear components
    du = ua_upper - ua_lower
    dv = va_upper - va_lower
    
    # Magnitude
    shear_magnitude = np.sqrt(du**2 + dv**2)
    
    # Direction (meteorological convention: direction FROM which wind is blowing)
    # atan2(dv, du) gives math convention (0° = east, counterclockwise)
    # Convert to meteorological convention (0° = north, clockwise)
    shear_direction = (270 - np.degrees(np.arctan2(dv, du))) % 360
    
    return shear_magnitude, shear_direction


def clean_attrs_for_netcdf(ds):
    """
    Clean dataset attributes to avoid errors during netCDF output.
    """
    for key in list(ds.attrs):
        val = ds.attrs[key]
        if isinstance(val, dict):
            del ds.attrs[key]
        elif isinstance(val, bool):
            ds.attrs[key] = int(val)
    
    for var in ds.variables:
        for key, val in list(ds[var].attrs.items()):
            if isinstance(val, dict):
                ds[var].attrs[key] = json.dumps(val)
            elif isinstance(val, bool):
                ds[var].attrs[key] = int(val)
    
    return ds


def process_month_data(ds_month_year, year_val, month, original_history, new_history, 
                      out_dir, model_name, time_res, zoom):
    """
    Process one month of data: compute wind shear and save to netCDF.
    """
    print(f"\nProcessing {year_val}-{month:02d}...")
    sys.stdout.flush()
    
    # Check if required variables exist
    required_vars = ['ua', 'va']
    missing_vars = [v for v in required_vars if v not in ds_month_year.data_vars]
    
    if missing_vars:
        print(f"  ERROR: Missing required variables: {missing_vars}")
        print(f"  Available variables: {list(ds_month_year.data_vars)}")
        sys.stdout.flush()
        return
    
    # Get pressure coordinate
    if 'pressure' not in ds_month_year.dims:
        print("  ERROR: No 'pressure' dimension found")
        sys.stdout.flush()
        return
    
    pressure_coord = ds_month_year['pressure']
    
    # Normalize pressure levels to dataset units
    low_shear_levels_hPa = [1000, 400]   # Low-shear: 1000 hPa - 400 hPa
    deep_shear_levels_hPa = [850, 100]   # Deep-shear: 850 hPa - 100 hPa
    
    low_shear_levels, units = normalize_pressure_levels(low_shear_levels_hPa, pressure_coord)
    deep_shear_levels, _ = normalize_pressure_levels(deep_shear_levels_hPa, pressure_coord)
    
    # ===== COMPUTE LOW SHEAR (400 hPa - 1000 hPa) =====
    print(f"  Computing low-shear (400 hPa - 1000 hPa)...")
    sys.stdout.flush()
    
    try:
        ua_1000 = ds_month_year['ua'].sel(pressure=low_shear_levels[0], method='nearest')
        va_1000 = ds_month_year['va'].sel(pressure=low_shear_levels[0], method='nearest')
        ua_400 = ds_month_year['ua'].sel(pressure=low_shear_levels[1], method='nearest')
        va_400 = ds_month_year['va'].sel(pressure=low_shear_levels[1], method='nearest')
        
        low_shear_mag, low_shear_dir = compute_wind_shear(ua_400, va_400, ua_1000, va_1000)
        
        low_shear_mag.attrs.update({
            'long_name': 'Low-Level Wind Shear Magnitude (400-1000 hPa)',
            'units': 'm s-1',
            'description': 'Magnitude of wind difference between 400 hPa and 1000 hPa',
            'formula': 'sqrt((u400-u1000)^2 + (v400-v1000)^2)'
        })
        
        low_shear_dir.attrs.update({
            'long_name': 'Low-Level Wind Shear Direction (400-1000 hPa)',
            'units': 'degrees',
            'description': 'Direction of wind shear vector (400 hPa - 1000 hPa)',
            'convention': 'Meteorological (0° = North, clockwise)'
        })
        
        print(f"    Low-shear computed successfully")
    except Exception as e:
        print(f"    ERROR computing low-shear: {e}")
        low_shear_mag = None
        low_shear_dir = None
    
    sys.stdout.flush()
    
    # ===== COMPUTE DEEP SHEAR (850 hPa - 100 hPa) =====
    print(f"  Computing deep-shear (850 hPa - 100 hPa)...")
    sys.stdout.flush()
    
    try:
        ua_850 = ds_month_year['ua'].sel(pressure=deep_shear_levels[0], method='nearest')
        va_850 = ds_month_year['va'].sel(pressure=deep_shear_levels[0], method='nearest')
        ua_100 = ds_month_year['ua'].sel(pressure=deep_shear_levels[1], method='nearest')
        va_100 = ds_month_year['va'].sel(pressure=deep_shear_levels[1], method='nearest')
        
        deep_shear_mag, deep_shear_dir = compute_wind_shear(ua_100, va_100, ua_850, va_850)
        
        deep_shear_mag.attrs.update({
            'long_name': 'Deep-Level Wind Shear Magnitude (850-100 hPa)',
            'units': 'm s-1',
            'description': 'Magnitude of wind difference between 100 hPa and 850 hPa',
            'formula': 'sqrt((u100-u850)^2 + (v100-v850)^2)'
        })
        
        deep_shear_dir.attrs.update({
            'long_name': 'Deep-Level Wind Shear Direction (850-100 hPa)',
            'units': 'degrees',
            'description': 'Direction of wind shear vector (100 hPa - 850 hPa)',
            'convention': 'Meteorological (0° = North, clockwise)'
        })
        
        print(f"    Deep-shear computed successfully")
    except Exception as e:
        print(f"    ERROR computing deep-shear: {e}")
        deep_shear_mag = None
        deep_shear_dir = None
    
    sys.stdout.flush()
    
    # ===== SAVE TO NETCDF =====
    output_vars = {}
    if low_shear_mag is not None:
        output_vars['low_shear_magnitude'] = low_shear_mag
        output_vars['low_shear_direction'] = low_shear_dir
    if deep_shear_mag is not None:
        output_vars['deep_shear_magnitude'] = deep_shear_mag
        output_vars['deep_shear_direction'] = deep_shear_dir
    
    if not output_vars:
        print("  No shear variables computed, skipping file output")
        sys.stdout.flush()
        return
    
    output_ds = xr.Dataset(output_vars)
    
    # Handle None values in time_res for NetCDF serialization
    time_res_str = time_res if time_res is not None else "N/A"
    
    out_file = os.path.join(out_dir, f"{model_name}_wind_shear_hp{zoom}_{time_res_str}.{year_val}{str(month).zfill(2)}.nc")
    
    # Handle existing files: append new variables if file exists
    if os.path.exists(out_file):
        print(f"  File exists, checking for new variables...")
        sys.stdout.flush()
        existing_ds = xr.open_dataset(out_file)
        new_vars = set(output_ds.data_vars) - set(existing_ds.data_vars)
        existing_ds.close()
        
        if new_vars:
            print(f"    Adding new variables: {new_vars}")
            for var in new_vars:
                v = clean_attrs_for_netcdf(output_ds[var])
                v.attrs.update({
                    "history": f"{new_history}; {original_history}",
                    "source_model": model_name,
                    "time_resolution": time_res_str,
                    "healpix_zoom": zoom,
                    "processing_script": "compute_wind_shear.py"
                })
                v.to_netcdf(out_file, mode='a', engine='h5netcdf')
            print(f"    Variables added to: {out_file}")
        else:
            print(f"    All variables already exist in file")
    else:
        output_ds = clean_attrs_for_netcdf(output_ds)
        output_ds.attrs.update({
            "history": f"{new_history}; {original_history}",
            "source_model": model_name,
            "time_resolution": time_res_str,
            "healpix_zoom": zoom,
            "processing_script": "compute_wind_shear.py",
            "description": "Wind shear computed between pressure levels"
        })
        output_ds.to_netcdf(out_file)
        print(f"  Created new file: {out_file}")
    
    sys.stdout.flush()


# =================== Main Pipeline =======================

def main():
    parser = argparse.ArgumentParser(
        description='Compute wind shear (low-shear and deep-shear) from model data.'
    )
    
    # Input/output options
    parser.add_argument('--catalog_url', 
                        default="https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml",
                        help='URL of the intake catalog (not used with --zarr_path)')
    parser.add_argument('--current_location', default="NERSC", 
                        help='Current location in catalog (NERSC or online) (not used with --zarr_path)')
    parser.add_argument('--catalog_model', default="scream_ne120", 
                        help='Model name in the catalog (not used with --zarr_path)')
    parser.add_argument('--model_time_freq', default=None,
                        help='Model output time frequency (e.g., "1H", "3H", "6H") - used to subsample track time steps')
    parser.add_argument('--catalog_params', default='{"zoom": 8}', 
                        help='JSON string of catalog parameters (not used with --zarr_path)')
    parser.add_argument('--zarr_path', default=None,
                        help='Path to zarr file for direct loading (e.g., ERA5). '
                             'If provided, catalog arguments are ignored. '
                             'Example: /pscratch/sd/w/wcmca1/hackathon/healpix/era5/era5_3H_zoom8_20190101_20211231_v0.zarr')
    parser.add_argument('--zarr_model_name', default='era5',
                        help='Model name for zarr files (used for output naming and model-specific fixes). Default: era5')
    parser.add_argument('--output_dir', required=True, 
                        help='Output directory for results')
    
    # Date filtering
    parser.add_argument('--start_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    print("=" * 70)
    print("Wind Shear Computation Script")
    print("=" * 70)
    print(f"Model: {args.catalog_model}")
    print(f"Location: {args.current_location}")
    print(f"Time resolution: {args.model_time_freq}")
    # print(f"Zoom level: {args.zoom}")
    print(f"Output directory: {args.output_dir}")
    if args.start_date and args.end_date:
        print(f"Date range: {args.start_date} to {args.end_date}")
    print("=" * 70)
    sys.stdout.flush()
    
    # =================================================================
    # LOAD DATASET: Either from zarr file or catalog
    # =================================================================
    
    # Parse catalog parameters (for zoom level)
    try:
        catalog_params = json.loads(args.catalog_params)
        zoom_level = catalog_params.get('zoom', 'unknown')
    except:
        catalog_params = {'zoom': 8}
        zoom_level = 8
    
    if args.zarr_path:
        # Direct zarr loading (e.g., ERA5, observations)
        print(f"\nLoading dataset from zarr file: {args.zarr_path}")
        sys.stdout.flush()
        
        ds = xr.open_dataset(args.zarr_path, engine='zarr')
        ds = ds.pipe(egh.attach_coords, signed_lon=True)
        
        # Convert time coordinate
        ds['time'] = xr.decode_cf(ds).indexes['time']
        
        # Apply model-specific fixes
        model_name = args.zarr_model_name
        ds = apply_model_fixes(ds, model_name)
        
        print(f"Loaded zarr dataset: {model_name}")
        print(f"Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
        print(f"Available variables: {list(ds.data_vars)}")
        sys.stdout.flush()
        
    else:
        # Catalog loading (e.g., SCREAM, ICON, IFS, NICAM, UM)
        print("\nLoading catalog and dataset...")
        sys.stdout.flush()
        
        # Open catalog and get dataset
        print(f"Opening catalog from {args.catalog_url}")
        sys.stdout.flush()
        cat = intake.open_catalog(args.catalog_url)[args.current_location]

        print(f"Loading dataset {args.catalog_model}...")
        sys.stdout.flush()

        # Add retry logic for dataset opening (handles intermittent 502 errors for IFS)
        max_retries = 10
        retry_delay = 10  # seconds
        
        for attempt in range(max_retries):
            try:
                ds = cat[args.catalog_model](**catalog_params).to_dask().pipe(
                    egh.attach_coords, signed_lon=True
                )
                
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
        
        # Convert time coordinate
        ds['time'] = xr.decode_cf(ds).indexes['time']
        
        # Apply model-specific fixes
        model_name = args.catalog_model
        ds = apply_model_fixes(ds, model_name)

    
    print(f"Dataset loaded. Dimensions: {dict(ds.dims)}")
    print(f"Available variables: {list(ds.data_vars)}")
    sys.stdout.flush()
    
    # Filter by date range if provided
    if args.start_date and args.end_date:
        print(f"\nFiltering data: {args.start_date} to {args.end_date}")
        sys.stdout.flush()
        ds = ds.sel(time=slice(args.start_date, args.end_date))
    
    # Get history attribute
    original_history = ds.attrs.get('history', '')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_history = f"{timestamp}: Wind shear computed by compute_wind_shear.py"
    
    # Process data by month
    print("\nProcessing data by month...")
    sys.stdout.flush()
    
    for month, ds_month in ds.groupby('time.month'):
        for year, ds_month_year in ds_month.groupby('time.year'):
            year_val = ds_month_year.coords['time'].dt.year[0].values
            
            process_month_data(
                ds_month_year, year_val, month, 
                original_history, new_history,
                args.output_dir, model_name, 
                args.model_time_freq, zoom_level
            )
    
    print("\n" + "=" * 70)
    print("Processing complete!")
    print("=" * 70)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
