"""
MCS Analysis Utilities

This module contains helper functions for MCS track filtering and environmental data processing.
Used in the analysis workflow for filtering MCS tracks and processing environmental variables.

Author: Laura Paccini
Last updated: January 2026
"""

import numpy as np
import pandas as pd
import xarray as xr
import glob
import os


# =============================================================================
# MCS TRACK FILTERING FUNCTIONS
# =============================================================================

def MCS_filter(ds_mcs, ilat=-30, elat=30, filter_split=True, min_ini_nonmcs=3, 
               nomerging=False, nopeak=False):
    """
    Apply comprehensive filtering criteria to MCS tracks.
    
    Filtering criteria:
    i)   MCS do not start with a split
    ii)  Tropical filter (latitude range)
    iii) Land fraction < 10% during whole lifetime
    iv)  No merging (start/end status constraints)
    v)   First time steps are non-MCS
    vi)  Stable MCS & total rain peak within MCS status
    
    Parameters:
    -----------
    ds_mcs : xarray.Dataset
        MCS track dataset with required variables (meanlat, meanlon, pf_landfrac, etc.)
    ilat : float
        Initial latitude for tropical filter (default: -30)
    elat : float
        End latitude for tropical filter (default: 30)
    filter_split : bool
        Whether to filter out tracks that start with a split (default: True)
    min_ini_nonmcs : int
        Minimum number of initial non-MCS time steps required (default: 3)
    nomerging : bool
        If True, skip merging filters (default: False)
    nopeak : bool
        If True, skip peak rain filter (default: False)
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with filtered MCS tracks and their statistics
    """
    
    # i) MCS do not start with a split
    if filter_split:
        mask = np.isnan(ds_mcs.start_split_cloudnumber)
        ds_nosplit = ds_mcs.sel(tracks=mask)
        del(ds_mcs)
        ds_mcs = ds_nosplit.copy()
    
    # Also apply spatial filtering
    initial_lats = ds_mcs.meanlat.isel(times=0).values
    initial_lons = ds_mcs.meanlon.isel(times=0).values
    
    # ii) Tropical filter (-30 to 30 latitude) & landfraction
    mask_tropical = (initial_lats >= ilat) & (initial_lats <= elat)
    mask_lf = ds_mcs.pf_landfrac.sum('times') < 0.1  # land fraction less than 10% during whole lifetime

    # iv) No merging
    mask_start_status = (ds_mcs.start_status == 1) | (ds_mcs.start_status == 2)
    mask_end_status = (ds_mcs.end_status == 0) | (ds_mcs.end_status == 3)

    # v) MCSs with first time steps are non MCSs
    mask_initial_non_mcs = ds_mcs.mcs_status.isel(times=slice(0, min_ini_nonmcs)).sum(dim='times') == 0
    mask_initial_non_mcs = mask_initial_non_mcs.drop_vars('times', errors='ignore')

    # vi) stable MCSs & total rain peak within MCS status
    # Sum the mcs_status (0s and 1s) over time. This sum must equal the total mcs_duration.
    mcs_hours_sum = ds_mcs.mcs_status.sum(dim='times')
    mask_continuous_mcs = (mcs_hours_sum == ds_mcs.mcs_duration)
    mask_continuous_mcs = mask_continuous_mcs.drop_vars('times', errors='ignore')

    # Total rainfall must peak during an MCS status (mcs_status == 1)
    peak_rain_time_idx = ds_mcs.total_rain.argmax(dim='times')
    status_at_peak_rain = ds_mcs.mcs_status.isel(times=peak_rain_time_idx)
    # The mask is true where that status is 1.
    mask_peak_rain = (status_at_peak_rain == 1)
    mask_peak_rain = mask_peak_rain.drop_vars('times', errors='ignore')

    # final extracted MCSs
    if nomerging:
        final_mcs = ((mask_tropical) & (mask_lf) & 
                     (mask_peak_rain) & (mask_initial_non_mcs) & (mask_continuous_mcs))
    elif nopeak:
        final_mcs = ((mask_tropical) & (mask_lf) & (mask_start_status) & (mask_end_status) & 
                     (mask_initial_non_mcs))
    else:
        final_mcs = ((mask_tropical) & (mask_lf) & (mask_start_status) & (mask_end_status) & 
                     (mask_peak_rain) & (mask_initial_non_mcs) & (mask_continuous_mcs))
    
    # Apply final combined mask
    final_ds = ds_mcs.where(final_mcs, drop=True)

    # Create a summary DataFrame
    tracks_of_interest = pd.DataFrame({
        'track_id': final_ds.tracks.values,
        'duration_hours': final_ds.track_duration.values,
        'time_to_max_area': final_ds.area.argmax(dim="times").values.astype(int),
        'time_to_max_total_rain': final_ds.total_rain.argmax(dim="times").values.astype(int),
        'initial_lat': final_ds.meanlat.isel(times=0).values,
        'initial_lon': final_ds.meanlon.isel(times=0).values,
        'lifetime_maxmax_pf_area': final_ds.pf_area.max('times').max('nmaxpf').values,
        'mean_area': final_ds.area.mean('times').values,
        'median_area': final_ds.area.median('times').values,
        'total_area': final_ds.area.sum('times').values,
        'max_total_rain': final_ds.total_rain.max('times').values,
        'mean_total_rain': final_ds.total_rain.mean('times').values,
        'median_total_rain': final_ds.total_rain.median('times').values,
        'total_total_rain': final_ds.total_rain.sum('times').values,
        'mean_pf_rain': final_ds.pf_rainrate.mean(['times', 'nmaxpf']).values,
        'median_pf_rain': final_ds.pf_rainrate.median(['times', 'nmaxpf']).values,
        'total_pf_rain': final_ds.pf_rainrate.sum(['times', 'nmaxpf']).values,
        'mean_landfrac': final_ds.pf_landfrac.mean('times').values,
        'total_landfrac': final_ds.pf_landfrac.sum('times').values,
        'start_time': final_ds.start_basetime.values,
        'mean_eccentricity': final_ds.pf_eccentricity.mean(['times', 'nmaxpf']).values,
        'mean_aspectratio': final_ds.pf_aspectratio.mean(['times', 'nmaxpf']).values,
        'mean_majoraxis': final_ds.pf_majoraxis.mean(['times', 'nmaxpf']).values,
        'mean_minoraxis': final_ds.pf_minoraxis.mean(['times', 'nmaxpf']).values,
        'mean_orientation': final_ds.pf_orientation.mean(['times', 'nmaxpf']).values,
        'median_eccentricity': final_ds.pf_eccentricity.median(['times', 'nmaxpf']).values,
        'median_aspectratio': final_ds.pf_aspectratio.median(['times', 'nmaxpf']).values,
        'median_majoraxis': final_ds.pf_majoraxis.median(['times', 'nmaxpf']).values,
        'median_minoraxis': final_ds.pf_minoraxis.median(['times', 'nmaxpf']).values,
        'median_orientation': final_ds.pf_orientation.median(['times', 'nmaxpf']).values
    })

    return tracks_of_interest


def remove_longdurations(df_model, feature='duration_hours', p_high=0.9):
    """
    Remove tracks with long durations based on percentile threshold.
    
    Parameters:
    -----------
    df_model : pd.DataFrame
        DataFrame with track statistics
    feature : str
        Column name for duration filtering (default: 'duration_hours')
    p_high : float
        Percentile threshold (default: 0.9)
    
    Returns:
    --------
    pd.DataFrame
        Filtered DataFrame with long durations removed
    """
    if df_model is None:
        return None
    q_high = df_model[feature].quantile(p_high)
    df_filtered = df_model[(df_model[feature] <= q_high)].copy()
    return df_filtered


# =============================================================================
# CIRCULAR LAND FRACTION FILTERING FUNCTIONS
# =============================================================================

def load_circular_land_fractions(lf_dir, track_models):
    """
    Load pre-computed circular land fraction data for all models.
    
    These land fractions are computed around MCS track positions using
    circular areas at multiple radii. This is separate from the MCS track
    filtering and is used as an additional quality filter.
    
    Parameters:
    -----------
    lf_dir : str
        Base directory containing land fraction parquet files
    track_models : list
        List of model names to load
    
    Returns:
    --------
    dict
        Dictionary mapping model name to land fraction DataFrame
    """
    
    # Map model names to land fraction file paths
    lf_file_map = {
        'scream': 'mcs_land_fractions_scream_ne120_zoom8_summary.parquet',
        'um': 'mcs_land_fractions_um_glm_n2560_RAL3p3_zoom8_summary.parquet',
        'icon': 'mcs_land_fractions_icon_d3hp003_zoom8_summary.parquet',
        'nicam': 'for_nicam/mcs_land_fractions_scream_ne120_zoom8_summary.parquet',
        'ifs': 'for_ifs/mcs_land_fractions_scream_ne120_zoom8_summary.parquet',
        'obs': 'for_era5/mcs_land_fractions_scream_ne120_zoom8_summary.parquet',
        'obs_v7': 'for_era5_imergv7/mcs_land_fractions_scream_ne120_zoom8_summary.parquet'
    }
    
    lf_data = {}
    for model in track_models:
        if model not in lf_file_map:
            print(f"Warning: No land fraction file mapping for {model}")
            lf_data[model] = None
            continue
        
        try:
            lf_path = os.path.join(lf_dir, lf_file_map[model])
            lf_data[model] = pd.read_parquet(lf_path)
            print(f"Loaded land fraction data for {model}: {len(lf_data[model])} records")
        except Exception as e:
            print(f"Warning: Could not load land fraction data for {model}. Error: {e}")
            lf_data[model] = None
    
    return lf_data


def apply_circular_land_fraction_filter(df_tracks, lf_data, radius=2, lf_thresh=0.1):
    """
    Filter tracks based on circular land fraction threshold.
    
    Merges track data with pre-computed circular land fractions and filters
    tracks where the land fraction exceeds the threshold.
    
    Parameters:
    -----------
    df_tracks : pd.DataFrame
        DataFrame with filtered track IDs and statistics
    lf_data : pd.DataFrame
        Land fraction data with columns: track_id, radius, total_land_fraction_track
    radius : float
        Radius to use for filtering (default: 2 degrees)
    lf_thresh : float
        Land fraction threshold (default: 0.1 = 10%)
    
    Returns:
    --------
    pd.DataFrame
        Tracks filtered by land fraction
    """
    if df_tracks is None or lf_data is None:
        return df_tracks
    
    # Filter land fraction data for the specified radius
    lf_radius = lf_data[lf_data['radius'] == radius].copy()
    
    # Merge with track data
    merged = pd.merge(
        df_tracks, 
        lf_radius[['track_id', 'total_land_fraction_track']], 
        on='track_id', 
        how='inner'
    )
    
    # Apply land fraction threshold
    filtered = merged[merged['total_land_fraction_track'] <= lf_thresh].copy()
    
    print(f"  Tracks before LF filter: {len(df_tracks)}")
    print(f"  Tracks after LF filter (r={radius}, thresh={lf_thresh}): {len(filtered)}")
    
    return filtered


# =============================================================================
# ENVIRONMENTAL DATA PROCESSING FUNCTIONS
# =============================================================================

def get_env_path(base_out_dir, model_name, var_name, env_model_dir_map, var_path_patterns):
    """
    Find the correct file path for a given model and variable.
    Handles inconsistent names and date stamps in environmental data files.
    
    Parameters:
    -----------
    base_out_dir : str
        Base output directory for environmental data
    model_name : str
        Model name from TRACK_MODELS (e.g., 'um', 'obs')
    var_name : str
        Variable name (e.g., 'prw', 'rh500')
    env_model_dir_map : dict
        Mapping from track model name to environmental data directory
    var_path_patterns : dict
        Variable path patterns for file searching
    
    Returns:
    --------
    str
        Full path to the environmental data file
    """
    
    # 1. Get the top-level directory name (e.g., 'UM_all' or 'era5')
    if model_name not in env_model_dir_map:
        raise KeyError(f"Model '{model_name}' not defined in ENV_MODEL_DIR_MAP.")
    model_dir = env_model_dir_map[model_name]
    
    # 2. Get the path pattern rule for this variable
    # Check for a model-specific override first (e.g., for 'obs')
    if model_name in var_path_patterns and var_name in var_path_patterns[model_name]:
        rule = var_path_patterns[model_name][var_name]
    # Otherwise, use the default rule
    elif var_name in var_path_patterns['default']:
        rule = var_path_patterns['default'][var_name]
    else:
        raise KeyError(f"Variable '{var_name}' not defined in VAR_PATH_PATTERNS.")
    
    pattern_type = rule['type']
    pattern = rule['pattern']
    
    # 3. Construct the full search path
    full_search_path = os.path.join(base_out_dir, model_dir, pattern)
    
    # 4. Find the file/directory
    if pattern_type == 'dir':
        # For 'dir' type, we just return the path as-is.
        return full_search_path
    
    elif pattern_type == 'glob':
        # For 'glob', we find all files matching the pattern
        search_results = glob.glob(full_search_path)
        
        if len(search_results) == 0:
            raise FileNotFoundError(f"No file found for {model_name}/{var_name}. "
                                    f"Searched: {full_search_path}")
        if len(search_results) > 1:
            # This is ambiguous, which is bad.
            raise FileNotFoundError(f"Multiple files found for {model_name}/{var_name}. "
                                    f"Searched: {full_search_path}. "
                                    f"Found: {search_results}")
        
        # Success! Return the one and only match.
        return search_results[0]


def get_filtered_df(df_main, df_tracks, lf_thresh=0.1, lf_var='total_land_fraction_track'):
    """
    Merge main data with track data and filter by circular land fraction threshold.
    
    Parameters:
    -----------
    df_main : pd.DataFrame
        Main environmental data DataFrame
    df_tracks : pd.DataFrame
        Track statistics DataFrame
    lf_thresh : float
        Land fraction threshold (default: 0.1)
    lf_var : str
        Column name for land fraction variable (default: 'total_land_fraction_track')
    
    Returns:
    --------
    pd.DataFrame
        Merged and filtered DataFrame
    """
    # Safe Merge (Inner Join) on track_id to ensure data integrity
    merged_df = pd.merge(df_main, df_tracks[['track_id', 'total_total_rain', lf_var]], 
                         on='track_id', how='inner')
    
    # Filter by Land Fraction Threshold
    final_df = merged_df[merged_df[lf_var] <= lf_thresh].copy()
    
    return final_df


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_environmental_data(main_dir, track_models, variables, env_model_dir_map, 
                            var_path_patterns, transform_config):
    """
    Load environmental data for all models and variables.
    
    Parameters:
    -----------
    main_dir : str
        Base directory for environmental data
    track_models : list
        List of model names
    variables : list
        List of variable names
    env_model_dir_map : dict
        Mapping from track model to environmental data directory
    var_path_patterns : dict
        Variable path patterns
    transform_config : dict
        Unit conversion configuration
    
    Returns:
    --------
    dict
        Nested dictionary: raw_env_data[model][var] = DataFrame
    """
    raw_env_data = {}
    for model in track_models:
        raw_env_data[model] = {}
        for var in variables:
            try:
                # 1. Find the path
                path = get_env_path(main_dir, model, var, env_model_dir_map, var_path_patterns)
                
                # 2. Load the data
                df = pd.read_parquet(path)
                
                # 3. Apply Transformation
                transform_func = transform_config.get(model, {}).get(var, lambda x: x)
                df_transformed = transform_func(df)
                
                # 4. Store the standardized DataFrame
                raw_env_data[model][var] = df_transformed
            except Exception as e:
                print(f"Warning: Could not load env data for {model} - {var}. Error: {e}")
                raw_env_data[model][var] = None
    
    return raw_env_data


def load_track_data(mcs_stats_dir, track_models, criteria, use_lf_filtered=True):
    """
    Load filtered MCS track data.
    
    Parameters:
    -----------
    mcs_stats_dir : str
        Directory containing filtered track pickle files
    track_models : list
        List of model names
    criteria : list
        List of filter criteria (e.g., ['all', 'min2'])
    use_lf_filtered : bool
        If True, load tracks already filtered by circular land fractions
        If False, load basic filtered tracks (before land fraction filtering)
    
    Returns:
    --------
    dict
        Nested dictionary: raw_track_data[model][crit] = DataFrame
    """
    raw_track_data = {}
    for model in track_models:
        raw_track_data[model] = {}
        for crit in criteria:
            try:
                crit_suffix = f'_{crit}' if crit != 'all' else ''
                
                if use_lf_filtered:
                    # Load tracks already filtered by circular land fractions
                    path = os.path.join(mcs_stats_dir, f'with_circular_lffiltered_{model}{crit_suffix}_r2.pkl')
                else:
                    # Load basic filtered tracks (before land fraction filtering)
                    path = os.path.join(mcs_stats_dir, f'df_trop_{model}{crit_suffix}.pkl')
                
                raw_track_data[model][crit] = pd.read_pickle(path)
            except Exception as e:
                print(f"Warning: Could not load track data for {model} - {crit}. Error: {e}")
                raw_track_data[model][crit] = None
    
    return raw_track_data


def process_all_data(raw_env_data, raw_track_data, track_models, variables, criteria):
    """
    Process all environmental data by filtering with track data and removing long durations.
    
    Parameters:
    -----------
    raw_env_data : dict
        Raw environmental data dictionary
    raw_track_data : dict
        Raw track data dictionary
    track_models : list
        List of model names
    variables : list
        List of variable names
    criteria : list
        List of filter criteria
    
    Returns:
    --------
    dict
        Nested dictionary: processed_data[model][crit][var] = DataFrame
    """
    processed_data = {}
    
    for model in track_models:
        processed_data[model] = {}
        for crit in criteria:
            base_track_df = raw_track_data[model].get(crit)
            
            if base_track_df is None:
                print(f"Skipping {model} - {crit}: Missing base track data.")
                continue
            
            long_removed_track_df = remove_longdurations(base_track_df)
            
            crit_key_base = crit
            crit_key_longremoved = f'{crit}_longremoved'
            
            processed_data[model][crit_key_base] = {}
            processed_data[model][crit_key_longremoved] = {}
            
            for var in variables:
                raw_env_df = raw_env_data[model].get(var)
                
                if raw_env_df is None:
                    continue
                
                processed_data[model][crit_key_base][var] = get_filtered_df(
                    raw_env_df, base_track_df
                )
                
                processed_data[model][crit_key_longremoved][var] = get_filtered_df(
                    raw_env_df, long_removed_track_df
                )
    
    print("Processing complete!")
    return processed_data
