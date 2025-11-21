"""
Utility functions for environmental variable extraction

Common functions shared between circular area extraction and mask-based extraction:
- Time conversion and alignment
- Pressure level handling
- Vertical velocity conversions (wa <-> omega)
- Model-specific fixes
- Surface wind computation

Author: Laura Paccini
Last updated: November 2025
"""

import numpy as np
import pandas as pd
import xarray as xr
import sys


def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):
        return pd.to_datetime([pd.Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second) 
                               for t in time_array])
    return time_array

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


def parse_pressure_levels(pressure_str):
    """Parse pressure levels string from bash to list"""
    try:
        return [float(p.strip()) for p in pressure_str.split(',')]
    except:
        return None


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
        pressure_levels_dataset = [p * 100 for p in pressure_levels_hPa]
        print(f"  Converting pressure levels from hPa to Pa: {pressure_levels_hPa} hPa → {pressure_levels_dataset} Pa")
    else:
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
        pressure_dataset = pressure_levels_dataset[i]
        
        print(f"  Processing level {pressure_hPa} hPa ({pressure_dataset} {pressure_units})...")
        sys.stdout.flush()
        
        # Select nearest pressure level
        w_level = w.sel(pressure=pressure_dataset, method='nearest')
        T_level = T.sel(pressure=pressure_dataset, method='nearest')
        
        # Convert pressure to Pa for density calculation if needed
        if pressure_units == 'hPa':
            pressure_Pa = pressure_dataset * 100
        else:
            pressure_Pa = pressure_dataset
        
        # Calculate air density: ρ = p / (R * T)
        rho = pressure_Pa / (R * T_level)
        
        # Calculate omega: ω = -ρgw
        omega_level = -rho * g * w_level
        omega_level = omega_level.assign_coords(pressure=pressure_hPa)
        
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
    
    return omega_combined


def convert_omega_to_w(ds, pressure_levels_hPa):
    """
    Convert pressure velocity (omega) to vertical velocity (w) using w = -ω/(ρg)
    
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
        pressure_dataset = pressure_levels_dataset[i]
        
        print(f"  Processing level {pressure_hPa} hPa ({pressure_dataset} {pressure_units})...")
        sys.stdout.flush()
        
        # Select nearest pressure level
        omega_level = omega.sel(pressure=pressure_dataset, method='nearest')
        T_level = T.sel(pressure=pressure_dataset, method='nearest')
        
        # Convert pressure to Pa for density calculation if needed
        if pressure_units == 'hPa':
            pressure_Pa = pressure_dataset * 100
        else:
            pressure_Pa = pressure_dataset
        
        # Calculate air density: ρ = p / (R * T)
        rho = pressure_Pa / (R * T_level)
        
        # Calculate wa: w = -ω/(ρg)
        wa_level = -omega_level / (rho * g)
        wa_level = wa_level.assign_coords(pressure=pressure_hPa)
        
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
    
    return wa_combined


def compute_surface_wind_speed(ds):
    """
    Compute surface wind speed (sfcWind) from horizontal wind components.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Must contain 'uas' and 'vas' variables (eastward and northward surface winds)
    
    Returns:
    --------
    xarray.DataArray
        Surface wind speed in m/s
    """
    print("  Computing surface wind speed (sfcWind) from uas and vas...")
    sys.stdout.flush()
    
    # Check if both components are available
    if 'uas' not in ds or 'vas' not in ds:
        raise ValueError("Both 'uas' and 'vas' required to compute sfcWind")
    
    # Compute wind speed: sqrt(u^2 + v^2)
    sfcWind = np.sqrt(ds['uas']**2 + ds['vas']**2)
    
    sfcWind.attrs = {
        'long_name': 'Near-Surface Wind Speed',
        'units': 'm s-1',
        'standard_name': 'wind_speed',
        'description': 'Surface wind speed computed from eastward and northward components',
        'formula': 'sqrt(uas^2 + vas^2)'
    }
    
    print("  Surface wind speed computed")
    sys.stdout.flush()
    return sfcWind


def compute_relative_humidity(ds):
    """
    Compute relative humidity (hur) from pressure, temperature, and specific humidity.
    
    Follows the WMO standard methodology (WMO Guide 8) using mixing ratios,
    similar to MetPy's implementation.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Must contain:
        - 'pressure': pressure coordinate (Pa or hPa, auto-detected)
        - 'ta': air temperature (K)
        - 'hus': specific humidity (kg/kg)
    
    Returns:
    --------
    xarray.DataArray
        Relative humidity in percent (0-100%)
    
    Notes:
    ------
    Formula (WMO eq. 4.A.16):
    1. Convert specific humidity to mixing ratio:
       w = q / (1 - q)
    2. Calculate saturation vapor pressure using Clausius-Clapeyron:
       es = 611.2 * exp(17.67 * (T - 273.15) / (T - 29.65))  [Pa]
    3. Calculate saturation mixing ratio:
       w_s = ε * es / (p - es)  where ε = 0.622
    4. Calculate relative humidity:
       RH = 100 * (w / (ε + w)) * ((ε + w_s) / w_s)
    
    References:
    - WMO Guide to Meteorological Instruments and Methods of Observation (WMO-No. 8)
    - Bolton (1980): The Computation of Equivalent Potential Temperature
    - MetPy library implementation
    """
    print("  Computing relative humidity (hur) from pressure, temperature, and specific humidity...")
    sys.stdout.flush()
    
    # Check required variables
    required_vars = ['ta', 'hus']
    missing_vars = [var for var in required_vars if var not in ds]
    if missing_vars:
        raise ValueError(f"Missing required variables for hur calculation: {missing_vars}")
    
    # Get variables
    T = ds['ta']  # temperature (K)
    q = ds['hus']  # specific humidity (kg/kg)
    
    # Get pressure coordinate
    if 'pressure' not in ds.coords and 'pressure' not in ds.dims:
        raise ValueError("Pressure coordinate 'pressure' not found in dataset")
    
    # Get pressure values and detect units
    if 'pressure' in ds.coords:
        pressure_coord = ds.coords['pressure']
    else:
        # If pressure is a dimension but not a coordinate, it might be in data_vars
        if 'pressure' in ds.data_vars:
            pressure_coord = ds['pressure']
        else:
            raise ValueError("Could not find pressure data in dataset")
    
    # Detect pressure units and convert to Pa if needed
    pressure_units = detect_pressure_units(pressure_coord)
    
    # Broadcast pressure to match data dimensions
    if 'pressure' in T.dims:
        # Pressure is a dimension - need to broadcast it
        if pressure_units == 'hPa':
            p = pressure_coord * 100  # Convert hPa to Pa
            print(f"    Converted pressure from hPa to Pa for calculation")
        else:
            p = pressure_coord  # Already in Pa
        
        # Broadcast pressure to match temperature shape
        p = p + 0 * T  # Broadcasting trick
    else:
        raise ValueError("Pressure must be a dimension of the temperature data")
    
    # Physical constants
    eps = 0.622  # Ratio of molecular weight of water vapor to dry air (ε)
    
    # Step 1: Convert specific humidity to mixing ratio
    # w = q / (1 - q)
    w = q / (1 - q)
    
    # Step 2: Calculate saturation vapor pressure using Clausius-Clapeyron (Bolton 1980)
    # es = 611.2 * exp(17.67 * (T - 273.15) / (T - 29.65))  [Pa]
    T_celsius = T - 273.15
    es = 611.2 * np.exp(17.67 * T_celsius / (T - 29.65))
    
    # Step 3: Calculate saturation mixing ratio
    # w_s = ε * es / (p - es)
    w_s = eps * es / (p - es)
    
    # Step 4: Calculate relative humidity (WMO formula)
    # RH = (w / (ε + w)) * ((ε + w_s) / w_s)
    # Convert to percentage
    hur = 100.0 * (w / (eps + w)) * ((eps + w_s) / w_s)
    
    # Clip to physical range [0, 100]
    hur = hur.clip(0, 100)
    
    # Add proper attributes
    hur.attrs = {
        'long_name': 'Relative Humidity',
        'units': '%',
        'standard_name': 'relative_humidity',
        'description': 'Relative humidity calculated from pressure, temperature, and specific humidity using WMO standard',
        'formula': 'RH = 100 * (w/(ε+w)) * ((ε+w_s)/w_s), where w = q/(1-q) and w_s = ε*es/(p-es)',
        'valid_range': '0 to 100',
        'reference': 'WMO Guide 8 eq. 4.A.16; Bolton (1980)'
    }
    
    print("  Relative humidity computed successfully")
    sys.stdout.flush()
    
    return hur


def apply_model_fixes(ds, model_name):
    """
    Apply model-specific fixes for dimension and variable names.
    
    Parameters:
    -----------
    ds : xarray.Dataset
        Input dataset
    model_name : str
        Model name (e.g., 'ifs', 'scream', 'nicam', 'icon', 'um')
    
    Returns:
    --------
    xarray.Dataset
        Fixed dataset with standardized names
    """
    print(f"\nApplying model-specific fixes for: {model_name}")
    sys.stdout.flush()
    
    # ===== FIX FOR IFS MODEL =====
    # IFS uses 'value' and 'cell' dimensions instead of standard names
    if 'value' in ds.dims and 'cell' in ds.dims:
        print("  Detected IFS model format (value/cell dimensions)")
        sys.stdout.flush()
        
        # Rename dimensions
        ds = ds.rename({'value': 'time', 'cell': 'ncells'})
        print("  Renamed: 'value' → 'time', 'cell' → 'ncells'")
        
        # IFS may have different variable names
        # var_rename_map = {}

        var_name_mapping = {
            't': 'ta',      # temperature
            'tcwv': 'prw',      # total column water vapor
            'w': 'omega',      # vertical velocity
            'q': 'hus',    # specific humidity
            'r': 'hur',     # relative humidity
            '2t': 'tas'  ,   # 2m temperature
            'sp': 'ps',     # surface pressure
            '10u': 'uas',   # 10m eastward wind
            '10v': 'vas',   # 10m northward wind
            '2d': 'tdas'    # 2m dew point temperature
        }
        
        vars_to_rename = {}
        for old_name, new_name in var_name_mapping.items():
            if old_name in ds.data_vars or old_name in ds.coords:
                vars_to_rename[old_name] = new_name
        
        # # Temperature: 't' → 'ta' or '2t' → 'tas'
        # if 't' in ds.data_vars and 'ta' not in ds.data_vars:
        #     var_rename_map['t'] = 'ta'
        # if '2t' in ds.data_vars and 'tas' not in ds.data_vars:
        #     var_rename_map['2t'] = 'tas'
        
        # # Specific humidity: 'q' → 'hus'
        # if 'q' in ds.data_vars and 'hus' not in ds.data_vars:
        #     var_rename_map['q'] = 'hus'
        
        # # Vertical velocity: 'w' → 'omega'
        # if 'w' in ds.data_vars and 'omega' not in ds.data_vars:
        #     var_rename_map['w'] = 'omega'
        
        # # Surface pressure: 'sp' → 'ps'
        # if 'sp' in ds.data_vars and 'ps' not in ds.data_vars:
        #     var_rename_map['sp'] = 'ps'
        
        # # Dew point: '2d' → 'tdas'
        # if '2d' in ds.data_vars and 'tdas' not in ds.data_vars:
        #     var_rename_map['2d'] = 'tdas'
        
        if vars_to_rename:
            ds = ds.rename(vars_to_rename)
            print(f"  Renamed variables: {vars_to_rename}")
        
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


# def subsample_tracks_by_frequency(df, model_time_freq):
#     """
#     Subsample track time steps to match model output frequency.
    
#     For hourly tracks, keep only times that align with model frequency.
#     For example, if model_time_freq='3H', keep only times at 00:00, 03:00, 06:00, etc.
    
#     Parameters:
#     -----------
#     df : pd.DataFrame
#         DataFrame with 'base_time' column (track times)
#     model_time_freq : str
#         Model frequency string (e.g., '1H', '3H', '6H')
    
#     Returns:
#     --------
#     pd.DataFrame
#         Subsampled DataFrame
#     """
#     print(f"Subsampling tracks to match model frequency: {model_time_freq}")
#     sys.stdout.flush()
    
#     # Parse frequency to hours
#     freq_hours = int(model_time_freq.replace('H', '').replace('h', ''))
    
#     # Convert base_time to datetime if needed
#     if not pd.api.types.is_datetime64_any_dtype(df['base_time']):
#         df['base_time'] = pd.to_datetime(df['base_time'])
    
#     # Keep only times where hour is divisible by freq_hours
#     mask = df['base_time'].dt.hour % freq_hours == 0
#     df_subsampled = df[mask].copy()
    
#     print(f"  Subsampled from {len(df)} to {len(df_subsampled)} time steps")
#     sys.stdout.flush()
    
#     return df_subsampled

# Define subsampling function
def subsample_tracks_by_frequency(df, model_freq):
    """
    Subsample track time steps to match model output frequency.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        Track dataframe with 'tracks'/'track_id', 'times'/'time_idx', and 'base_time' columns. 
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

    # Determine which column name is used
    track_col = 'tracks' if 'tracks' in df.columns else 'track_id'
    time_col = 'times' if 'times' in df.columns else 'time_idx'
    
    # Convert frequency string to timedelta
    freq_td = pd.Timedelta(model_freq)
    
    # Group by track and filter
    filtered_rows = []
    for track_id, track_group in df.groupby(track_col):
        # Sort by time
        track_group = track_group.sort_values(time_col)
        
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


def align_track_times_to_model_frequency(df, model_freq):
    """
    Two-step process: subsample tracks to model frequency, then align to model output times.
    
    Step 1: Subsample each track to model frequency starting from initiation time
            (e.g., if track starts at 04:00, subsample to 04:00, 07:00, 10:00, ... for 3H freq)
    
    Step 2: Align subsampled times to nearest available model output times
            (e.g., 04:00→03:00, 07:00→06:00, 10:00→09:00 for model times at 00, 03, 06, 09, ...)
    
    This ensures:
    - Track initiation is always preserved
    - Track is sampled every N hours from its start
    - Extraction uses nearest available model time
    - Time offsets are calculated from track start (subsampled base_time)
    
    Parameters:
    -----------
    df : pd.DataFrame
        Track dataframe with 'track_id', 'time_idx', and 'base_time' columns
    model_freq : str
        Model frequency (e.g., '3H')
    
    Returns:
    --------
    pd.DataFrame
        Subsampled DataFrame with:
        - 'base_time': Subsampled track times (original)
        - 'extraction_time': Aligned model times (for extraction)
    """
    print(f"\nSubsampling tracks and aligning to model frequency: {model_freq}")
    sys.stdout.flush()
    
    # Parse frequency (e.g., '3H' → 3 hours)
    freq_hours = int(model_freq.rstrip('H'))
    
    # Determine column names (backwards compatibility)
    track_col = 'tracks' if 'tracks' in df.columns else 'track_id'
    time_col = 'times' if 'times' in df.columns else 'time_idx'
    
    original_count = len(df)
    
    # Step 1: Subsample each track to model frequency from its start
    print(f"  Step 1: Subsampling tracks every {freq_hours} hours from initiation...")
    sys.stdout.flush()
    
    subsampled_rows = []
    for track_id, track_group in df.groupby(track_col):
        # Sort by time index
        track_group = track_group.sort_values(time_col).reset_index(drop=True)
        
        # Keep every Nth row (where N = freq_hours for hourly data)
        # This preserves initiation (index 0) and samples every freq_hours steps
        # For 3H freq on hourly data: keep indices 0, 3, 6, 9, ...
        indices_to_keep = track_group.index[::freq_hours]
        subsampled_rows.append(track_group.loc[indices_to_keep])
    
    df_subsampled = pd.concat(subsampled_rows, ignore_index=True)
    subsampled_count = len(df_subsampled)
    
    print(f"  Subsampled from {original_count} to {subsampled_count} time points")
    print(f"  Reduction: {(1 - subsampled_count/original_count)*100:.1f}%")
    sys.stdout.flush()
    
    # Step 2: Align subsampled times to nearest model output times
    print(f"  Step 2: Aligning to nearest model output times...")
    sys.stdout.flush()
    
    base_times = pd.to_datetime(df_subsampled['base_time'])
    
    # Round to nearest model time (00:00, 03:00, 06:00, etc.)
    # Strategy: Convert to total hours since epoch, round to nearest multiple of freq_hours
    # 04:00 → 03:00 (nearest)
    # 07:00 → 06:00 (nearest)
    
    # Get timestamp in nanoseconds, convert to hours
    hours_since_epoch = base_times.astype('int64') / (3600 * 1e9)
    
    # Round to nearest multiple of freq_hours
    rounded_hours = np.round(hours_since_epoch / freq_hours) * freq_hours
    
    # Convert back to datetime
    df_subsampled['extraction_time'] = pd.to_datetime(rounded_hours * 3600 * 1e9, unit='ns')
    
    # Report alignment statistics
    unique_base = base_times.nunique()
    unique_extraction = df_subsampled['extraction_time'].nunique()
    print(f"  Unique subsampled times: {unique_base}")
    print(f"  Unique extraction times: {unique_extraction}")
    print(f"  Final track-time combinations: {len(df_subsampled)}")
    sys.stdout.flush()
    
    return df_subsampled
