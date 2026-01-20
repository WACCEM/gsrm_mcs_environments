import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore", category=FutureWarning) # don't warn us about future package conflicts

import pandas as pd
import xarray as xr
import numpy as np
from datetime import datetime
from matplotlib.lines import Line2D

def filter_tracks_by_initiation(df, min_duration=6, require_split_nan=True, require_mcs_status_zero=True):
    """
    Filter MCS tracks based on initiation criteria.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame with MCS track statistics
    min_duration : int, default=6
        Minimum track duration in hours
    require_split_nan : bool, default=True
        If True, keep only tracks where start_split_cloudnumber is NaN
    require_mcs_status_zero : bool, default=True
        If True, keep only tracks with mcs_status=0 at initiation
    
    Returns:
    --------
    pandas.DataFrame
        Filtered DataFrame containing only tracks that meet the criteria
    """
    # Start with all tracks
    filtered_df = df.copy()
    
    # Filter by minimum duration
    if min_duration > 0:
        filtered_df = filtered_df[filtered_df['track_duration'] >= min_duration]
        print(f"Filtered to {len(filtered_df.track.unique())} tracks with duration >= {min_duration}h")
    
    # Filter by start_split_cloudnumber
    if require_split_nan:
        # Group by track to get unique tracks
        track_groups = filtered_df.groupby('track')
        
        # Find tracks where start_split_cloudnumber is NaN for all entries
        valid_tracks = []
        for track, group in track_groups:
            if group['start_split_cloudnumber'].isna().all():
                valid_tracks.append(track)
        
        filtered_df = filtered_df[filtered_df['track'].isin(valid_tracks)]
        print(f"Filtered to {len(valid_tracks)} tracks with start_split_cloudnumber = NaN")
    
    # Filter by mcs_status
    if require_mcs_status_zero:
        # Group by track
        track_groups = filtered_df.groupby('track')
        
        # Find tracks where initial mcs_status is 0
        valid_tracks = []
        for track, group in track_groups:
            # Get rows at time_offset_hours = 0 (initiation)
            init_rows = group[group['time_offset_hours'] == 0]
            
            if len(init_rows) > 0 and init_rows['mcs_status'].iloc[0] == 0:
                valid_tracks.append(track)
        
        filtered_df = filtered_df[filtered_df['track'].isin(valid_tracks)]
        print(f"Filtered to {len(valid_tracks)} tracks with mcs_status = 0 at initiation")
    
    return filtered_df



def evolution_by_radius(df, stat_var='mean', #min_duration=6, time_range=(-24, 24), 
                           title=None, radii=None, single_radius=None):
    """
    Plot the evolution of a statistic for different radii, or for a single radius.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame with MCS track statistics
    stat_var : str, default='mean'
        Statistical variable to plot ('mean', 'std', 'median', etc.)
    min_duration : int, default=6
        Minimum track duration in hours
    time_range : tuple, default=(-24, 24)
        Time range to plot (hours relative to initiation)
    title : str, optional
        Plot title
    radii : list, optional
        List of radii to include. If None, use all radii in df.
        Ignored if single_radius is specified.
    single_radius : float, optional
        If specified, plot only this radius. Overrides radii parameter.
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with columns for radius, time_offset_hours, mean, std, and count
    """

    
    # # Filter by minimum duration
    # if min_duration > 0:
    #     filtered_df = df[df['track_duration'] >= min_duration]
    # else:
    #     filtered_df = df
    filtered_df = df
    # If single_radius is specified, it takes precedence over radii
    if single_radius is not None:
        radii = [single_radius]
    # Get unique radii if not specified
    elif radii is None:
        radii = sorted(filtered_df['radius'].unique())
        
    # Filter data to include only the specified radii
    filtered_df = filtered_df[filtered_df['radius'].isin(radii)]
    
    # # Filter by time range
    # filtered_df = filtered_df[
    #     (filtered_df['time_offset_hours'] >= time_range[0]) & 
    #     (filtered_df['time_offset_hours'] <= time_range[1])
    # ]

    # Create empty lists to store results
    all_radii = []
    all_times = []
    all_means = []
    all_stds = []
    all_counts = []
    
    # Process each radius
    for radius in radii:
        radius_df = filtered_df[filtered_df['radius'] == radius]
        
        # Group by time offset and calculate mean of the statistic
        time_groups = radius_df.groupby('time_offset_hours')
        
        for time, group in time_groups:
            all_radii.append(radius)
            all_times.append(time)
            all_means.append(group[stat_var].mean())
            all_stds.append(group[stat_var].std())
            all_counts.append(len(group))
        
    # Create result DataFrame
    result_df = pd.DataFrame({
        'radius': all_radii,
        'time_offset_hours': all_times,
        'mean': all_means,
        'std': all_stds,
        'count': all_counts
    })
    
    # Sort by radius and time
    result_df = result_df.sort_values(['radius', 'time_offset_hours'])
    
    return result_df


def group_by_timeoffset(df, stat_var='mean',):
    # Group by time offset and calculate mean of the statistic
    time_groups = df.groupby('time_offset_hours')
    # Create empty lists to store results
    all_times = []
    all_means = []
    all_stds = []
    all_counts = []
    
    for time, group in time_groups:
        all_times.append(time)
        all_means.append(group[stat_var].mean())
        all_stds.append(group[stat_var].std())
        all_counts.append(len(group))
        
    # Create result DataFrame
    result_df = pd.DataFrame({
        'time_offset_hours': all_times,
        'mean': all_means,
        'std': all_stds,
        'count': all_counts
    })
    
    # Sort by radius and time
    result_df = result_df.sort_values(['time_offset_hours'])
    
    return result_df

def get_extreme_cases_data(df, mcs_feature='track_duration', stat_var='mean', radius=2.0,
                         percentile_high=90, percentile_low=10, min_duration=6, 
                         time_range=(-24, 24), time_bin_size=3):
    """
    Return data for extreme cases based on MCS feature percentiles.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame with MCS track statistics
    mcs_feature : str, default='track_duration'
        MCS feature to categorize by ('pf_area', 'area', 'track_duration', 'pf_rainrate', etc.)
        These are used to group tracks into high/low categories.
    stat_var : str, default='mean'
        Environmental variable to analyze ('mean', 'std', 'median', etc.)
    radius : float, default=2.0
        Radius value to use for analysis
    percentile_high : int, default=90
        Upper percentile for extreme cases
    percentile_low : int, default=10
        Lower percentile for extreme cases
    min_duration : int, default=6
        Minimum track duration in hours (ignored if mcs_feature is 'track_duration')
    time_range : tuple, default=(-24, 24)
        Time range to analyze (hours relative to initiation)
    time_bin_size : int, default=3
        Size of time bins in hours for aggregation
        
    Returns:
    --------
    dict
        Dictionary containing:
        - 'high_data': DataFrame with time-binned data for high percentile cases
        - 'low_data': DataFrame with time-binned data for low percentile cases
        - 'high_tracks': List of track IDs in high percentile group
        - 'low_tracks': List of track IDs in low percentile group
        - 'threshold_high': High percentile threshold value
        - 'threshold_low': Low percentile threshold value
        - 'feature': Name of feature used for categorization
    """
    
    import warnings
    import numpy as np
    import pandas as pd
    
    # Warn if user is trying to analyze an MCS feature (which would only show post-initiation values)
    mcs_specific_vars = ['pf_rainrate', 'pf_area', 'area', 'total_rain']
    if stat_var in mcs_specific_vars:
        warnings.warn(
            f"You're using '{stat_var}' as stat_var which typically only exists post-initiation. "
            f"This will not show pre-initiation values. "
            f"For environmental evolution analysis, use 'mean' or another environmental variable."
        )
        
    # If mcs_feature is track_duration, skip the min_duration filter
    if mcs_feature == 'track_duration':
        filtered_df = df
    elif min_duration > 0:
        filtered_df = df[df['track_duration'] >= min_duration]
    else:
        filtered_df = df
    
    # Filter by radius
    filtered_df = filtered_df[filtered_df['radius'] == radius]
    
    # Filter by time range
    filtered_df = filtered_df[
        (filtered_df['time_offset_hours'] >= time_range[0]) & 
        (filtered_df['time_offset_hours'] <= time_range[1])
    ]
    
    # Calculate average values of the mcs_feature for each track
    # For most features, use post-initiation values (time_offset_hours >= 0)
    track_properties = {}
    for track in filtered_df['track'].unique():
        track_data = filtered_df[filtered_df['track'] == track]
        
        # Use post-initiation data for feature calculation (except duration)
        if mcs_feature != 'track_duration':
            post_init_data = track_data[track_data['time_offset_hours'] >= 0]
            if len(post_init_data) > 0:
                feature_val = post_init_data[mcs_feature].mean() if not post_init_data[mcs_feature].isna().all() else np.nan
            else:
                feature_val = np.nan
        else:
            # For duration, use the track_duration value directly
            feature_val = track_data['track_duration'].iloc[0] if not track_data['track_duration'].isna().all() else np.nan
        
        if not np.isnan(feature_val):
            track_properties[track] = feature_val
    
    # Create DataFrame for sorting
    prop_df = pd.DataFrame(list(track_properties.items()), columns=['track', mcs_feature])
    prop_df = prop_df.dropna()
    
    # Determine thresholds
    high_threshold = prop_df[mcs_feature].quantile(percentile_high/100)
    low_threshold = prop_df[mcs_feature].quantile(percentile_low/100)
    
    # Get the high and low tracks
    high_tracks = prop_df[prop_df[mcs_feature] >= high_threshold]['track'].tolist()
    low_tracks = prop_df[prop_df[mcs_feature] <= low_threshold]['track'].tolist()
    
    # Function to aggregate data by time bins
    def aggregate_by_time(track_list):
        # Create time bins
        time_bins = np.arange(time_range[0], time_range[1] + time_bin_size, time_bin_size)
        binned_data = {t: [] for t in time_bins[:-1]}
        
        # Collect values for each time bin
        for track in track_list:
            track_data = filtered_df[filtered_df['track'] == track]
            
            for i in range(len(time_bins)-1):
                start_time = time_bins[i]
                end_time = time_bins[i+1]
                bin_data = track_data[(track_data['time_offset_hours'] >= start_time) & 
                                     (track_data['time_offset_hours'] < end_time)]
                if not bin_data.empty:
                    binned_data[start_time].extend(bin_data[stat_var].values)
        
        # Calculate statistics for each bin
        result_data = []
        
        for i in range(len(time_bins)-1):
            bin_center = (time_bins[i] + time_bins[i+1]) / 2
            
            if binned_data[time_bins[i]]:
                bin_mean = np.nanmean(binned_data[time_bins[i]])
                bin_std = np.nanstd(binned_data[time_bins[i]])
                bin_count = len(binned_data[time_bins[i]])
            else:
                bin_mean = np.nan
                bin_std = np.nan
                bin_count = 0
            
            result_data.append({
                'time_bin_start': time_bins[i],
                'time_bin_end': time_bins[i+1],
                'time_bin_center': bin_center,
                'mean': bin_mean,
                'std': bin_std,
                'count': bin_count
            })
        
        return pd.DataFrame(result_data)
    
    # Aggregate data
    high_data = aggregate_by_time(high_tracks)
    low_data = aggregate_by_time(low_tracks)
    
    # Add category labels
    high_data['category'] = 'high'
    low_data['category'] = 'low'
    
    return {
        'high_data': high_data,
        'low_data': low_data,
        'high_tracks': high_tracks,
        'low_tracks': low_tracks,
        'threshold_high': high_threshold,
        'threshold_low': low_threshold,
        'feature': mcs_feature
    }


def plot_multi_variable_evolution(variable_dfs, nrows=None, ncols=None, figsize=None, 
                               time_range=(-24, 24), radii=None, single_radius=None,
                               variable_units=None, share_y=False, fontsize=10):
    """
    Plot the evolution of multiple variables by radius in a grid of subplots.
    
    Parameters:
    -----------
    variable_dfs : dict
        Dictionary mapping variable names to their evolution DataFrames.
        Each DataFrame should have columns: 'radius', 'time_offset_hours', 'mean'
    nrows, ncols : int, optional
        Number of rows and columns in the subplot grid. If not specified,
        they will be calculated automatically.
    figsize : tuple, optional
        Figure size (width, height) in inches. Default is calculated based on number of variables.
    time_range : tuple, default=(-24, 24)
        Time range to plot (hours relative to initiation)
    radii : list, optional
        List of radii to include. If None, use all radii in the DataFrames.
    single_radius : float, optional
        If specified, plot only this radius. Overrides radii parameter.
    variable_units : dict, optional
        Dictionary mapping variable names to their units for y-axis labels
    share_y : bool, default=False
        Whether to share y-axis limits across all subplots
    fontsize : int, default=10
        Base font size for plot elements
    
    Returns:
    --------
    matplotlib.figure.Figure
        Figure object containing the multi-panel plot
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    
    # Determine grid dimensions
    n_vars = len(variable_dfs)
    if nrows is None and ncols is None:
        ncols = int(np.ceil(np.sqrt(n_vars)))
        nrows = int(np.ceil(n_vars / ncols))
    elif nrows is None:
        nrows = int(np.ceil(n_vars / ncols))
    elif ncols is None:
        ncols = int(np.ceil(n_vars / nrows))
    
    # Calculate figure size if not provided
    if figsize is None:
        figsize = (ncols * 4, nrows * 3)
    
    # Create figure and axes grid
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True, sharey=share_y,
                           constrained_layout=True)
    
    # Flatten axes array for easy iteration if there are multiple subplots
    if n_vars > 1:
        if nrows == 1 and ncols == 1:
            axes = np.array([axes])
        axes_flat = axes.flatten()
    else:
        axes_flat = np.array([axes])
    
    # Create a color map for radius values
    if single_radius is not None:
        all_radii = [single_radius]
    elif radii is not None:
        all_radii = radii
    else:
        # Collect all unique radii across dataframes
        all_radii = set()
        for df in variable_dfs.values():
            all_radii.update(df['radius'].unique())
        all_radii = sorted(all_radii)
    
    # Use a colormap that works well for categorical data
    colors = plt.cm.tab10(np.linspace(0, 1, min(10, len(all_radii))))
    radius_colors = {rad: colors[i % len(colors)] for i, rad in enumerate(all_radii)}
    
    # Plot each variable in its own subplot
    for i, (var_name, df) in enumerate(variable_dfs.items()):
        if i >= len(axes_flat):
            print(f"Warning: More variables than subplot space. Skipping {var_name}.")
            continue
        
        ax = axes_flat[i]
        
        # Filter data by time range
        df_time_filtered = df[(df['time_offset_hours'] >= time_range[0]) & 
                             (df['time_offset_hours'] <= time_range[1])]
        
        # Filter by radii
        if single_radius is not None:
            radii_to_plot = [single_radius]
            df_filtered = df_time_filtered[df_time_filtered['radius'] == single_radius]
        elif radii is not None:
            radii_to_plot = radii
            df_filtered = df_time_filtered[df_time_filtered['radius'].isin(radii)]
        else:
            radii_to_plot = sorted(df_time_filtered['radius'].unique())
            df_filtered = df_time_filtered
        
        # Plot each radius
        for radius in radii_to_plot:
            radius_df = df_filtered[df_filtered['radius'] == radius].copy()
            
            if len(radius_df) > 0:
                # Sort by time for consistent line plotting
                radius_df = radius_df.sort_values('time_offset_hours')
                
                ax.plot(radius_df['time_offset_hours'], radius_df['mean'], 'o-', 
                       color=radius_colors[radius], linewidth=1.5, markersize=4,
                       label=f'{radius}° (~{radius*111:.0f} km)')
        
        # Add vertical line at time = 0
        ax.axvline(x=0, color='gray', linestyle='--')
        
        # Add labels and title
        ax.set_xlabel('Time Relative to MCS Initiation (hours)', fontsize=fontsize)
        if variable_units and var_name in variable_units:
            ax.set_ylabel(f'{var_name} ({variable_units[var_name]})', fontsize=fontsize)
        else:
            ax.set_ylabel(var_name, fontsize=fontsize)
        
        ax.set_title(var_name, fontsize=fontsize+2)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='both', which='major', labelsize=fontsize-2)
    
    # Remove empty subplots
    for i in range(n_vars, len(axes_flat)):
        axes_flat[i].set_visible(False)
    
    # Add a common legend for all subplots
    legend_elements = [
        Line2D([0], [0], color=radius_colors[radius], marker='o', linestyle='-',
              label=f'{radius}° (~{radius*100:.0f} km)')
        for radius in radii_to_plot
    ]
    legend_elements.append(Line2D([0], [0], color='gray', linestyle='--', 
                                 label='MCS Initiation'))
    
    fig.legend(handles=legend_elements, loc='upper center', 
              bbox_to_anchor=(0.5, 0.02), ncol=min(5, len(radii_to_plot)+1),
              fontsize=fontsize)
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.1)  # Make room for the legend
    
    return fig


def plot_multi_variable_extremes(extreme_cases_results, vars_to_plot=None, rows=3, cols=3, 
                                 variable_units=None, radius=None, figsize=(15, 12), sharey=False):
    """
    Plot high vs low extreme cases for multiple variables.
    
    Parameters:
    -----------
    extreme_cases_results : dict
        Dictionary of results from get_extreme_cases_data for each variable
    vars_to_plot : list, optional
        List of variable names to plot. If None, plot all variables.
    rows, cols : int
        Number of rows and columns for the subplot grid
    variable_units : dict, optional
        Dictionary mapping variable names to their units for y-axis labels
    figsize : tuple
        Figure size (width, height) in inches
    sharey : bool
        Whether to share y-axis scales across subplots
    """
    if vars_to_plot is None:
        vars_to_plot = list(extreme_cases_results.keys())
    
    # Set up the figure and axes
    fig, axes = plt.subplots(rows, cols, figsize=figsize, sharex=True, sharey=sharey)
    axes = axes.flatten()  # Flatten to make indexing easier
    
    # Plot each variable
    for i, var_name in enumerate(vars_to_plot):
        if i >= len(axes):
            print(f"Warning: Not enough subplots for {var_name}")
            continue
            
        ax = axes[i]
        result = extreme_cases_results[var_name]
        
        # Get data
        high_data = result['high_data']
        low_data = result['low_data']
        
        # Plot high and low categories
        ax.plot(high_data['time_bin_center'], high_data['mean'], 'o-', 
                color='red', label=f'Highest {100-percentile_high}%')
        ax.plot(low_data['time_bin_center'], low_data['mean'], 's--', 
                color='blue', label=f'Lowest {percentile_low}%')
        
        # Add vertical line at time = 0
        ax.axvline(x=0, color='gray', linestyle='--')
        
        # Add labels
        
        if variable_units and var_name in variable_units:
            ax.set_ylabel(f'{var_name} ({variable_units[var_name]})', fontsize=fontsize)
        else:
            ax.set_ylabel(var_name, fontsize=fontsize)
            
        ax.set_title(f'{var_name}', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # Only add x-label for bottom row
        if i >= len(vars_to_plot) - cols:
            ax.set_xlabel('Time Relative to MCS Initiation (hours)')
    
    # Hide unused subplots
    for i in range(len(vars_to_plot), len(axes)):
        axes[i].set_visible(False)
    
    # Add a common legend
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 0.02), 
              ncol=3, fontsize=12)
    
    # Add a title for the entire figure
    feature_desc = mcs_feature.replace('_', ' ').title()
    fig.suptitle(f'Variable Evolution by MCS {feature_desc} (Radius = {radius}°)', 
                 fontsize=13, y=0.98)
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.92, bottom=0.08)
    
    return fig




def plot_multi_variable_model_comparison(variable_dfs_model1, variable_dfs_model2, 
                                       model1_label="Model 1", model2_label="Model 2",
                                       nrows=None, ncols=None, figsize=None, 
                                       time_range=(-24, 24), radii=[2.0, 3.5],
                                       variable_units=None, share_y=False, fontsize=10):
    """
    Plot the evolution of multiple variables comparing two models with specific radii.
    
    Parameters:
    -----------
    variable_dfs_model1 : dict
        Dictionary mapping variable names to their evolution DataFrames for model 1.
        Each DataFrame should have columns: 'radius', 'time_offset_hours', 'mean'
    variable_dfs_model2 : dict
        Dictionary mapping variable names to their evolution DataFrames for model 2.
    model1_label, model2_label : str
        Labels for the two models (e.g., "SCREAM", "ICON")
    nrows, ncols : int, optional
        Number of rows and columns in the subplot grid. If not specified,
        they will be calculated automatically.
    figsize : tuple, optional
        Figure size (width, height) in inches. Default is calculated based on number of variables.
    time_range : tuple, default=(-24, 24)
        Time range to plot (hours relative to initiation)
    radii : list, default=[2.0, 3.5]
        List of radii to include in the comparison
    variable_units : dict, optional
        Dictionary mapping variable names to their units for y-axis labels
    share_y : bool, default=False
        Whether to share y-axis limits across all subplots
    fontsize : int, default=10
        Base font size for plot elements
    
    Returns:
    --------
    matplotlib.figure.Figure
        Figure object containing the multi-panel comparison plot
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    
    # Get common variables between both models
    common_vars = set(variable_dfs_model1.keys()) & set(variable_dfs_model2.keys())
    if not common_vars:
        raise ValueError("No common variables found between the two models")
    
    common_vars = sorted(common_vars)
    n_vars = len(common_vars)
    
    # Determine grid dimensions
    if nrows is None and ncols is None:
        ncols = int(np.ceil(np.sqrt(n_vars)))
        nrows = int(np.ceil(n_vars / ncols))
    elif nrows is None:
        nrows = int(np.ceil(n_vars / ncols))
    elif ncols is None:
        ncols = int(np.ceil(n_vars / nrows))
    
    # Calculate figure size if not provided
    if figsize is None:
        figsize = (ncols * 4, nrows * 3)
    
    # Create figure and axes grid
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True, sharey=share_y,
                           constrained_layout=True)
    
    # Flatten axes array for easy iteration if there are multiple subplots
    if n_vars > 1:
        if nrows == 1 and ncols == 1:
            axes = np.array([axes])
        axes_flat = axes.flatten()
    else:
        axes_flat = np.array([axes])
    
    # Define colors and line styles for models and radii
    model_colors = {'model1': 'blue', 'model2': 'red'}
    radius_styles = {radii[0]: '-', radii[1]: '--'}  # solid for first radius, dashed for second
    radius_markers = {radii[0]: 'o', radii[1]: 's'}  # circle for first radius, square for second
    
    # Plot each variable in its own subplot
    for i, var_name in enumerate(common_vars):
        if i >= len(axes_flat):
            print(f"Warning: More variables than subplot space. Skipping {var_name}.")
            continue
        
        ax = axes_flat[i]
        
        # Process both models
        for model_key, (model_dfs, model_label, model_color) in enumerate([
            (variable_dfs_model1, model1_label, model_colors['model1']),
            (variable_dfs_model2, model2_label, model_colors['model2'])
        ]):
            
            df = model_dfs[var_name]
            
            # Filter data by time range
            df_time_filtered = df[(df['time_offset_hours'] >= time_range[0]) & 
                                 (df['time_offset_hours'] <= time_range[1])]
            
            # Filter by specified radii
            df_filtered = df_time_filtered[df_time_filtered['radius'].isin(radii)]
            
            # Plot each radius for this model
            for radius in radii:
                radius_df = df_filtered[df_filtered['radius'] == radius].copy()
                
                if len(radius_df) > 0:
                    # Sort by time for consistent line plotting
                    radius_df = radius_df.sort_values('time_offset_hours')
                    
                    # Create label
                    label = f'{model_label} - {radius}° (~{radius*111:.0f} km)'
                    
                    ax.plot(radius_df['time_offset_hours'], radius_df['mean'], 
                           linestyle=radius_styles[radius],
                           marker=radius_markers[radius],
                           color=model_color, 
                           linewidth=2, 
                           markersize=4,
                           alpha=0.8,
                           label=label)
        
        # Add vertical line at time = 0
        ax.axvline(x=0, color='gray', linestyle=':', alpha=0.7)
        
        # Add labels and title
        ax.set_xlabel('Time Relative to MCS Initiation (hours)', fontsize=fontsize)
        if variable_units and var_name in variable_units:
            ax.set_ylabel(f'{var_name} ({variable_units[var_name]})', fontsize=fontsize)
        else:
            ax.set_ylabel(var_name, fontsize=fontsize)
        
        ax.set_title(var_name, fontsize=fontsize+2, )
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='both', which='major', labelsize=fontsize-2)
        
        # Add legend to first subplot only to avoid clutter
        # if i == 0:
        #     ax.legend(fontsize=fontsize-2, loc='best')
    
    # Remove empty subplots
    for i in range(n_vars, len(axes_flat)):
        axes_flat[i].set_visible(False)
    
    # Add a main title for the entire figure
    fig.suptitle(f'Environmental Variable Evolution: {model1_label} vs {model2_label}', 
                fontsize=fontsize+4,  y=0.98)
    
    # Create a comprehensive legend at the bottom
    legend_elements = []
    
    # Add model color legend
    legend_elements.extend([
        Line2D([0], [0], color=model_colors['model1'], linewidth=2, 
               label=model1_label),
        Line2D([0], [0], color=model_colors['model2'], linewidth=2, 
               label=model2_label)
    ])
    
    # Add radius style legend
    legend_elements.extend([
        Line2D([0], [0], color='black', linestyle=radius_styles[radii[0]], 
               marker=radius_markers[radii[0]], label=f'{radii[0]}° (~{radii[0]*111:.0f} km)'),
        Line2D([0], [0], color='black', linestyle=radius_styles[radii[1]], 
               marker=radius_markers[radii[1]], label=f'{radii[1]}° (~{radii[1]*111:.0f} km)')
    ])
    
    # Add initiation line
    legend_elements.append(Line2D([0], [0], color='gray', linestyle=':', 
                                 label='MCS Initiation'))
    
    fig.legend(handles=legend_elements, loc='lower center', 
              bbox_to_anchor=(0.5, 0.02), ncol=5, fontsize=fontsize)
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=-0.12)  # Make room for the legend
    
    return fig


def plot_multi_variable_all_comparison(variable_dfs_dict, 
                                       nrows=None, ncols=None, figsize=None, 
                                       time_range=(-24, 24), radii=[2.0, 3.5],xlimi=-24,xlimf=24,
                                       variable_units=None, share_y=False, fontsize=10):
    """
    Plot the evolution of multiple variables comparing multiple models/observations.
    Each subplot shows one variable with all available models that have that variable.
    
    Parameters:
    -----------
    variable_dfs_dict : dict
        Dictionary where keys are model names and values are dictionaries mapping 
        variable names to their evolution DataFrames.
        Example: {
            'Observations': {'temp': df1, 'humidity': df2, ...},
            'ICON': {'temp': df3, 'pressure': df4, ...},
            'SCREAM': {'temp': df5, 'humidity': df6, ...},
            'UM': {'pressure': df7, ...}
        }
    nrows, ncols : int, optional
        Number of rows and columns in the subplot grid. If not specified,
        they will be calculated automatically.
    figsize : tuple, optional
        Figure size (width, height) in inches. Default is calculated based on number of variables.
    time_range : tuple, default=(-24, 24)
        Time range to plot (hours relative to initiation)
    radii : list, default=[2.0, 3.5]
        List of radii to include in the comparison
    variable_units : dict, optional
        Dictionary mapping variable names to their units for y-axis labels
    share_y : bool, default=False
        Whether to share y-axis limits across all subplots
    fontsize : int, default=10
        Base font size for plot elements
    
    Returns:
    --------
    matplotlib.figure.Figure
        Figure object containing the multi-panel comparison plot
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    
    # Define colors for each model (matching your existing color scheme)
    model_colors = {
        'ERA5': 'gray', 
        'ICON': '#ff7f0e', 
        'SCREAM': '#2ca02c', 
        'UM': 'salmon'
    }
    
    # Collect all unique variables across all models
    all_variables = set()
    for model_name, model_vars in variable_dfs_dict.items():
        all_variables.update(model_vars.keys())
    
    all_variables = sorted(all_variables)
    n_vars = len(all_variables)
    
    if n_vars == 0:
        raise ValueError("No variables found in any model")
    
    # Determine grid dimensions
    if nrows is None and ncols is None:
        ncols = int(np.ceil(np.sqrt(n_vars)))
        nrows = int(np.ceil(n_vars / ncols))
    elif nrows is None:
        nrows = int(np.ceil(n_vars / ncols))
    elif ncols is None:
        ncols = int(np.ceil(n_vars / nrows))
    
    # Calculate figure size if not provided
    if figsize is None:
        figsize = (ncols * 4, nrows * 3)
    
    # Create figure and axes grid
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True, sharey=share_y,
                           constrained_layout=True)
    
    # Flatten axes array for easy iteration if there are multiple subplots
    if n_vars > 1:
        if nrows == 1 and ncols == 1:
            axes = np.array([axes])
        axes_flat = axes.flatten()
    else:
        axes_flat = np.array([axes])
    
    # Define line styles and markers for radii
    radius_styles =  '-' # radii[1]: '--'}  # solid for first radius, dashed for second
    radius_markers = 'o'# radii[1]: 's'}  # circle for first radius, square for second
    
    # # If we have more than 2 radii, extend the styles
    # if len(radii) > 2:
    #     additional_styles = ['-.', ':'] * (len(radii) // 2)
    #     additional_markers = ['^', 'D', 'v', '<', '>', 'p', '*'] * (len(radii) // 7 + 1)
        
    #     for i, radius in enumerate(radii):
    #         if radius not in radius_styles:
    #             radius_styles[radius] = additional_styles[i % len(additional_styles)]
    #             radius_markers[radius] = additional_markers[i % len(additional_markers)]
    
    # Plot each variable in its own subplot
    models_plotted = set()  # Track which models we actually plot
    
    for i, var_name in enumerate(all_variables):
        if i >= len(axes_flat):
            print(f"Warning: More variables than subplot space. Skipping {var_name}.")
            continue
        
        ax = axes_flat[i]
        variable_has_data = False
        
        # Process each model for this variable
        for model_name, model_vars in variable_dfs_dict.items():
            # Check if this model has this variable
            if var_name not in model_vars:
                continue
                
            df = model_vars[var_name]
            
            # Filter data by time range
            df_time_filtered = df[(df['time_offset_hours'] >= time_range[0]) & 
                                 (df['time_offset_hours'] <= time_range[1])]
            
            # Filter by specified radii
            df_filtered = df_time_filtered[df_time_filtered['radius'].isin(radii)]
            
            # Get color for this model
            model_color = model_colors.get(model_name, 'black')  # default to black if not found
            
            # Plot each radius for this model
            for radius in radii:
                radius_df = df_filtered[df_filtered['radius'] == radius].copy()
                
                if len(radius_df) > 0:
                    variable_has_data = True
                    models_plotted.add(model_name)
                    
                    # Sort by time for consistent line plotting
                    radius_df = radius_df.sort_values('time_offset_hours')
                    
                    # Create label
                    label = f'{model_name} - {radius}° (~{radius*111:.0f} km)'
                    
                    ax.plot(radius_df['time_offset_hours'], radius_df['mean'], 
                           linestyle=radius_styles[radius],
                           marker=radius_markers[radius],
                           color=model_color, 
                           linewidth=2, 
                           markersize=4,
                           alpha=0.8,
                           label=label)
        
        # Only format the subplot if we have data
        if variable_has_data:
            # Add vertical line at time = 0
            ax.axvline(x=0, color='gray', linestyle=':', alpha=0.7)
            
            # Add labels and title
            ax.set_xlabel('Time Relative to MCS Initiation (hours)', fontsize=fontsize)
            ax.set_xlim(xlimi,xlimf)
            if variable_units and var_name in variable_units:
                ax.set_ylabel(f'{var_name} ({variable_units[var_name]})', fontsize=fontsize)
            else:
                ax.set_ylabel(var_name, fontsize=fontsize)
            
            ax.set_title(var_name, fontsize=fontsize+2)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='both', which='major', labelsize=fontsize-2)
        else:
            # If no data, hide the subplot
            ax.set_visible(False)
    
    # Remove empty subplots
    for i in range(n_vars, len(axes_flat)):
        axes_flat[i].set_visible(False)
    
    # Add a main title for the entire figure
    model_names = list(models_plotted)
    if len(model_names) > 2:
        title_models = ', '.join(model_names[:-1]) + f' and {model_names[-1]}'
    else:
        title_models = ' vs '.join(model_names)
    
    fig.suptitle(f'Environmental Variable Evolution: {title_models}', 
                fontsize=fontsize+4, y=0.98)
    
    # Create a comprehensive legend at the bottom
    legend_elements = []
    
    # Add model color legend (only for models that were actually plotted)
    for model_name in sorted(models_plotted):
        legend_elements.append(
            Line2D([0], [0], color=model_colors.get(model_name, 'black'), 
                   linewidth=2, label=model_name)
        )
    
    # Add radius style legend
    for radius in radii:
        legend_elements.append(
            Line2D([0], [0], color='black', linestyle=radius_styles[radius], 
                   marker=radius_markers[radius], 
                   label=f'{radius}° (~{radius*111:.0f} km)')
        )
    
    # Add initiation line
    legend_elements.append(Line2D([0], [0], color='gray', linestyle=':', 
                                 label='MCS Initiation'))
    
    # Calculate number of columns for legend
    ncol_legend = min(len(legend_elements), 6)  # Max 6 columns
    
    fig.legend(handles=legend_elements, loc='lower center', 
              bbox_to_anchor=(0.5, 0.02), ncol=ncol_legend, fontsize=fontsize)
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)  # Make room for the legend
    
    return fig


def plot_single_radius_comparison(variable_dfs_dict,
                                  radius=2.0,
                                  nrows=None, ncols=None, figsize=None,
                                  time_range=(-24, 24), xlimi=-24, xlimf=24,
                                  variable_units=None, share_y=False, fontsize=10,suptitle=False):
    """
    Plot the evolution of multiple variables for a single radius, comparing multiple models.
    Each subplot shows one variable with all available models that have that variable.
    X-axis labels are only shown on the bottom row of subplots.

    Parameters:
    -----------
    variable_dfs_dict : dict
        Dictionary where keys are model names and values are dictionaries mapping
        variable names to their evolution DataFrames.
    radius : float, default=2.0
        The specific radius in degrees to plot.
    nrows, ncols : int, optional
        Number of rows and columns in the subplot grid. Calculated automatically if not specified.
    figsize : tuple, optional
        Figure size (width, height) in inches.
    time_range : tuple, default=(-24, 24)
        Time range to plot (hours relative to initiation).
    variable_units : dict, optional
        Dictionary mapping variable names to their units for y-axis labels.
    share_y : bool, default=False
        Whether to share y-axis limits across all subplots.
    fontsize : int, default=10
        Base font size for plot elements.

    Returns:
    --------
    matplotlib.figure.Figure
        Figure object containing the multi-panel comparison plot.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D

    # Define colors for each model
    model_colors = {
        'ERA5_IMERGv7': 'k',
        'ERA5_IMERGv6': 'gray',
        'ICON': '#ff7f0e',
        'SCREAM': '#2ca02c',
        'UM': 'salmon',
        'IFS':"steelblue", "NICAM":"mediumpurple"
    }

    # Collect all unique variables across all models
    all_variables = sorted({
        var for model_vars in variable_dfs_dict.values() for var in model_vars.keys()
    })
    
    n_vars = len(all_variables)
    if n_vars == 0:
        raise ValueError("No variables found in any model")

    # Determine grid dimensions
    if nrows is None and ncols is None:
        ncols = int(np.ceil(np.sqrt(n_vars)))
        nrows = int(np.ceil(n_vars / ncols))
    elif nrows is None:
        nrows = int(np.ceil(n_vars / ncols))
    elif ncols is None:
        ncols = int(np.ceil(n_vars / nrows))

    # Calculate figure size if not provided
    if figsize is None:
        figsize = (ncols * 4, nrows * 3)

    # Create figure and axes grid
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True, sharey=share_y,
                               constrained_layout=True)
    axes_flat = axes.flatten() if n_vars > 1 else np.array([axes])

    # Plot each variable in its own subplot
    models_plotted = set()

    for i, var_name in enumerate(all_variables):
        if i >= len(axes_flat):
            print(f"Warning: More variables than subplot space. Skipping {var_name}.")
            continue
        
        ax = axes_flat[i]
        variable_has_data = False

        # Process each model for this variable
        for model_name, model_vars in variable_dfs_dict.items():
            if var_name not in model_vars:
                continue

            df = model_vars[var_name]

            # Filter data by time range and the single specified radius
            if radius:
                df_filtered = df[
                    (df['time_offset_hours'] >= time_range[0]) &
                    (df['time_offset_hours'] <= time_range[1]) &
                    (df['radius'] == radius)
                ].copy()
            else:
                df_filtered = df[
                    (df['time_offset_hours'] >= time_range[0]) &
                    (df['time_offset_hours'] <= time_range[1]) 
                ].copy()
                
            

            if not df_filtered.empty:
                variable_has_data = True
                models_plotted.add(model_name)
                
                df_filtered.sort_values('time_offset_hours', inplace=True)
                
                model_color = model_colors.get(model_name, 'black')
                
                ax.plot(df_filtered['time_offset_hours'], df_filtered['mean'],
                        linestyle='-',
                        marker='o',
                        color=model_color,
                        linewidth=2,
                        markersize=4,
                        alpha=0.8,
                        label=model_name)

        # Format the subplot only if it has data
        if variable_has_data:
            ax.axvline(x=0, color='gray', linestyle=':', alpha=0.7)
            
            # --- MODIFICATION START ---
            # Only add xlabel to subplots in the bottom row
            # The starting index for the last row is (nrows - 1) * ncols
            if i >= (nrows - 1) * ncols:
                ax.set_xlabel('Time Relative to MCS Initiation (hours)', fontsize=fontsize)
            # --- MODIFICATION END ---
            
            ax.set_xlim(xlimi, xlimf)
            ylabel = f'{var_name} ({variable_units[var_name]})' if variable_units and var_name in variable_units else var_name
            ax.set_ylabel(ylabel, fontsize=fontsize)
            ax.set_title('')
            # ax.set_title(var_name, fontsize=fontsize + 1)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='both', which='major', labelsize=fontsize - 2)
        else:
            ax.set_visible(False)

    # Hide any unused subplots
    for i in range(n_vars, len(axes_flat)):
        axes_flat[i].set_visible(False)

    # Create a main title for the entire figure
    model_names_str = ' vs '.join(sorted(models_plotted))
    if suptitle:
        fig.suptitle(f'Environmental Variable Evolution at {radius}° (~{radius*111:.0f} km) Radius: {model_names_str}',
                 fontsize=fontsize + 1, y=0.98)

    # Create a comprehensive legend at the bottom
    legend_elements = [
        Line2D([0], [0], color=model_colors.get(name, 'black'), linewidth=2, label=name)
        for name in sorted(models_plotted)
    ]
    legend_elements.append(Line2D([0], [0], color='gray', linestyle=':', label='MCS Initiation'))

    fig.legend(handles=legend_elements, loc='lower center',
               bbox_to_anchor=(0.5, -0.1), ncol=min(len(legend_elements), 5), fontsize=fontsize)
    
    fig.tight_layout(rect=[0, 0.05, 1, 0.98])

    return fig, axes_flat


def plot_correlation_matrix(var_dfs_dict, time_window=(-6, 0), radius=2.0,
                            mcs_stats_df=None, mcs_stats_cols=None,
                            mask_upper=True, figsize=(10, 8), cmap='RdBu_r',
                            vmin=-1, vmax=1, annot=True, fontsize=10, title=None):
    """
    Plot a correlation matrix of environmental variables within a time window.
    
    Parameters:
    -----------
    var_dfs_dict : dict
        Dictionary mapping variable names to their DataFrames.
        Each DataFrame should have columns: 'track_id', 'radius', 'time_offset_hours', 'mean'
    time_window : tuple, default=(-6, 0)
        Time window to compute correlations (hours relative to initiation).
        For pre-convective conditions, use negative values (e.g., (-6, 0)).
    radius : float, default=2.0
        Radius value to filter data.
    mcs_stats_df : pandas.DataFrame, optional
        DataFrame containing MCS-specific statistics (e.g., df_trop_scream_all).
        Should have 'track_id' column and columns specified in mcs_stats_cols.
    mcs_stats_cols : list of str, optional
        List of column names from mcs_stats_df to include in correlation analysis.
        Examples: ['total_total_rain', 'duration_hours', 'total_area']
    mask_upper : bool, default=True
        If True, mask the upper triangle of the correlation matrix.
    figsize : tuple, default=(10, 8)
        Figure size (width, height) in inches.
    cmap : str, default='RdBu_r'
        Colormap for the correlation matrix.
    vmin, vmax : float, default=-1, 1
        Min and max values for the colormap.
    annot : bool, default=True
        If True, annotate cells with correlation values.
    fontsize : int, default=10
        Base font size for plot elements.
    title : str, optional
        Custom title for the plot. If None, a default title will be generated.
    
    Returns:
    --------
    matplotlib.figure.Figure
        Figure object containing the correlation matrix plot.
    pandas.DataFrame
        Correlation matrix as a DataFrame.
    """
    import matplotlib.pyplot as plt
    import pandas as pd
    import numpy as np
    
    # Filter data for the specified radius and time window
    filtered_data = {}
    for var_name, df in var_dfs_dict.items():
        # Filter by radius
        df_filtered = df[df['radius'] == radius].copy()
        
        # Filter by time window
        df_filtered = df_filtered[
            (df_filtered['time_offset_hours'] >= time_window[0]) & 
            (df_filtered['time_offset_hours'] <= time_window[1])
        ]
        
        # Group by track_id and compute mean across the time window
        # This gives us one value per track for each variable
        df_agg = df_filtered.groupby('track_id')['mean'].mean()
        
        filtered_data[var_name] = df_agg
    
    # Create a DataFrame with all variables
    correlation_df = pd.DataFrame(filtered_data)
    
    # Add MCS statistics if provided
    if mcs_stats_df is not None and mcs_stats_cols is not None:
        # Ensure mcs_stats_cols is a list
        if isinstance(mcs_stats_cols, str):
            mcs_stats_cols = [mcs_stats_cols]
        
        # Extract relevant columns from MCS stats DataFrame
        mcs_stats_subset = mcs_stats_df[['track_id'] + mcs_stats_cols].copy()
        
        # Set track_id as index for merging
        mcs_stats_subset.set_index('track_id', inplace=True)
        
        # Merge with correlation_df
        # Use inner join to keep only tracks present in both DataFrames
        correlation_df = correlation_df.join(mcs_stats_subset, how='inner')
    
    # Drop tracks with any missing values
    correlation_df = correlation_df.dropna()
    
    # Compute correlation matrix
    corr_matrix = correlation_df.corr()
    
    # Create mask for upper triangle if requested
    # For rectangular matrices (env vars vs MCS stats), adjust masking
    n_vars = len(corr_matrix)
    if mask_upper:
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    else:
        mask = None
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot correlation matrix
    if mask_upper:
        # Manually plot with masked upper triangle
        im = ax.imshow(np.ma.masked_where(mask, corr_matrix), 
                      cmap=cmap, vmin=vmin, vmax=vmax, aspect='auto')
    else:
        im = ax.imshow(corr_matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect='auto')
    
    # Set ticks and labels
    ax.set_xticks(np.arange(len(corr_matrix.columns)))
    ax.set_yticks(np.arange(len(corr_matrix.columns)))
    ax.set_xticklabels(corr_matrix.columns, fontsize=fontsize)
    ax.set_yticklabels(corr_matrix.columns, fontsize=fontsize)
    
    # Rotate x-axis labels for better readability
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    
    # Add annotations if requested
    if annot:
        for i in range(len(corr_matrix.columns)):
            for j in range(len(corr_matrix.columns)):
                # Skip upper triangle if masked
                if mask_upper and j > i:
                    continue
                text = ax.text(j, i, f'{corr_matrix.iloc[i, j]:.2f}',
                             ha="center", va="center", color="black", fontsize=fontsize-2)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Correlation Coefficient', fontsize=fontsize)
    cbar.ax.tick_params(labelsize=fontsize-2)
    
    # Set title
    if title is None:
        title = f'Correlation Matrix of Environmental Variables\n' \
                f'Time Window: {time_window[0]} to {time_window[1]} hours | ' \
                f'Radius: {radius}° (~{radius*111:.0f} km) | ' \
                f'N tracks: {len(correlation_df)}'
    ax.set_title(title, fontsize=fontsize+2, pad=20)
    
    # Adjust layout
    plt.tight_layout()
    
    return fig, corr_matrix

from scipy.stats import pearsonr, spearmanr
import matplotlib.patches as patches
import matplotlib.gridspec as gridspec
import matplotlib as mpl
from matplotlib.colors import Normalize
import matplotlib.cm as cm

def pearsonr_pvalues(df):
    # Create an empty DataFrame with the same columns and indices as 'df'
    p = pd.DataFrame(index=df.columns, columns=df.columns)
    
    # Iterate over each pair of columns
    for r in df.columns:
        for c in df.columns:
            # Filter rows where both columns have non-null values
            tmp = df[df[r].notnull() & df[c].notnull()]
            # Find non-NaN values for both
            mask = np.logical_and(~np.isnan(tmp[r]), ~np.isnan(tmp[c]))
            if not tmp.empty:
                # Calculate Pearson correlation and p-value, then assign the p-value
                correlation, p_value = pearsonr(tmp[r][mask], tmp[c][mask])
                p.loc[r, c] = round(p_value, 4)
    
    return p

def spearmanr_pvalues(df):
    # Create an empty DataFrame with the same columns and indices as 'df'
    p = pd.DataFrame(index=df.columns, columns=df.columns)
    
    # Iterate over each pair of columns
    for r in df.columns:
        for c in df.columns:
            # Filter rows where both columns have non-null values
            tmp = df[df[r].notnull() & df[c].notnull()]
            if not tmp.empty:
                # Calculate Spearman correlation and p-value, then assign the p-value
                correlation, p_value = spearmanr(tmp[r], tmp[c])
                p.loc[r, c] = round(p_value, 4)
    
    return p

def custom_correlogram(corr_df, p_df, var_groups, group_colors, group_names, 
                      figsize=(12, 12), figname=None,
                      title='Correlogram', alpha_nonsig=0.5,
                      cmap='coolwarm', vmin=-1, vmax=1, p_thresh=0.05,
                      fontsize=12, title_fontsize=20, title_pos=0.9, 
                      cbar_label='Correlation Coefficient', border_columns=None):
    """
    Create a custom correlogram with grouped variables and significance visualization.
    
    Parameters:
    -----------
    corr_df : pandas.DataFrame
        Correlation matrix
    p_df : pandas.DataFrame  
        P-value matrix
    var_groups : list of lists
        Groups of variable names, e.g., [['var1', 'var2'], ['var3', 'var4']]
    group_colors : list
        Colors for each group, e.g., ['blue', 'red', 'green']
    group_names : list
        Names for each group, e.g., ['Group 1', 'Group 2']
    figsize : tuple
        Figure size
    figname: string
        Figure name
    title : str
        Plot title
    alpha_nonsig : float
        Alpha value for non-significant correlations
    cmap : str
        Colormap name
    vmin, vmax : float
        Color scale limits
    p_thresh : float
        P-value threshold for significance
    fontsize : int
        Base font size
    title_fontsize : int
        Title font size
    cbar_label: string
        Title for colorbar.
    border_columns : int, optional
        Number of columns to surround with a black border
        
    Returns:
    --------
    fig, ax : matplotlib figure and axis objects
    """

    
    # Set up the figure with white background
    fig = plt.figure(figsize=figsize, facecolor='white')
    
    # Create gridspec with left margin for group names
    # [left margin for group names, main plot, gap, colorbar]
    gs = gridspec.GridSpec(1, 4, figure=fig, width_ratios=[0.25, 1, 0.01, 0.05], wspace=0.05, hspace=0)

    mpl.rcParams['font.family'] = 'DejaVu Sans'
    
    # Main plot axis (skip the left margin)
    ax = fig.add_subplot(gs[0, 1])
    ax.set_facecolor('white')
    
    # Colorbar axis
    cax = fig.add_subplot(gs[0, 3])
    
    # Create colormap
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap_obj = cm.get_cmap(cmap)
    
    # Get the size of the correlation matrix
    n_vars = len(corr_df)
    
    # Create variable to group mapping
    var_to_group = {}
    var_to_color = {}
    for i, group in enumerate(var_groups):
        for var in group:
            var_to_group[var] = i
            var_to_color[var] = group_colors[i]
    
    # Plot the heatmap manually
    for i in range(n_vars):
        for j in range(n_vars):
            if i <= j:  # Upper triangle (including diagonal)
                continue
                
            # Get correlation and p-value
            corr_val = corr_df.iloc[i, j]
            p_val = p_df.iloc[i, j]
            
            # Skip if correlation or p-value is NaN
            if pd.isna(corr_val) or pd.isna(p_val):
                continue
                
            # Determine color and alpha based on significance
            color = cmap_obj(norm(corr_val))
            alpha = 1.0 if p_val < p_thresh else alpha_nonsig
            text_color = 'black' if p_val < p_thresh else 'gray'
            
            # Plot the cell
            rect = patches.Rectangle((j, n_vars-1-i), 1, 1, facecolor=color, alpha=alpha, edgecolor='white', linewidth=0.5)
            ax.add_patch(rect)
            
            # Add correlation text
            ax.text(j + 0.5, n_vars-1-i + 0.5, f'{corr_val:.2f}', ha='center', va='center', color=text_color, 
                   fontsize=fontsize*0.7, weight='normal')
    
    # Set up the basic plot properties
    ax.set_xlim(0, n_vars)
    ax.set_ylim(0, n_vars)
    ax.set_aspect('equal')
    
    # Set ticks and labels with colors
    var_names = corr_df.columns.tolist()
    
    # X-axis labels (bottom)
    ax.set_xticks(np.arange(n_vars) + 0.5)
    ax.set_xticklabels(var_names, rotation=45, ha='right', fontsize=fontsize-1)
    
    # Color x-axis labels
    for i, (tick_label, var_name) in enumerate(zip(ax.get_xticklabels(), var_names)):
        if var_name in var_to_color:
            tick_label.set_color(var_to_color[var_name])
    
    # Y-axis labels (left side) - reversed order for correct positioning
    reversed_var_names = var_names[::-1]
    ax.set_yticks(np.arange(n_vars) + 0.5)
    ax.set_yticklabels(reversed_var_names, fontsize=fontsize-1)
    
    # Color y-axis labels
    for i, (tick_label, var_name) in enumerate(zip(ax.get_yticklabels(), reversed_var_names)):
        if var_name in var_to_color:
            tick_label.set_color(var_to_color[var_name])
    
    # Add horizontal lines to separate groups
    y_positions = []
    current_pos = 0
    
    for group in var_groups:
        current_pos += len(group)
        if current_pos < n_vars:  # Don't add line after last group
            y_pos = n_vars - current_pos
            ax.axhline(y=y_pos, color='black', linewidth=5, alpha=1, xmax=(n_vars - y_pos - 1)/n_vars)
            y_positions.append(y_pos)
    
    # Add group labels in the left margin using axis coordinates for proper positioning
    current_pos = 0
    for i, (group, group_name, color) in enumerate(zip(var_groups, group_names, group_colors)):
        group_size = len(group)
        # Calculate the middle position of the group in data coordinates
        group_start = n_vars - current_pos
        group_end = n_vars - (current_pos + group_size)
        group_middle = (group_start + group_end) / 2
        
        # Convert to axis coordinates (0 to 1 range)
        y_axis_coord = group_middle / n_vars
        
        # Add group label in the left margin using axis coordinates
        ax.text(-0.3, y_axis_coord, group_name, 
                ha='center', va='center', fontsize=fontsize*1.2, 
                weight='bold', color=color, rotation=0,
                transform=ax.transAxes)
        
        current_pos += group_size
    
    # Set title
    fig.suptitle(title, fontsize=title_fontsize, weight='bold', y=title_pos)

    # Remove spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    # NOW create the colorbar - after all axis modifications are complete
    # Force a draw to finalize the main axis positioning
    fig.canvas.draw()
    
    # Get the actual position of the main axis after all modifications
    main_pos = ax.get_position()
    
    # Set the colorbar axis to match the main axis vertical extent
    cbar_pos = cax.get_position()
    cax.set_position([cbar_pos.x0, main_pos.y0, cbar_pos.width, main_pos.height])
    
    # Create the colorbar
    cbar = plt.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap_obj), cax=cax)
    cbar.set_label(cbar_label, fontsize=fontsize)

    # Add border around specified columns AFTER everything else is set up
    if border_columns is not None and border_columns > 0:
        border_columns = min(border_columns, n_vars)  # Don't exceed total columns
        border_rect = patches.Rectangle((0.0, 0.0), border_columns, n_vars, linewidth=3, edgecolor='black', 
                                      facecolor='none', zorder=100, clip_on=False)
        ax.add_patch(border_rect)
    
    # Save the figure
    if figname is not None:
        fig.savefig(figname, bbox_inches='tight', dpi=300, facecolor='w')
        print(f"Saved: {figname}")

    return fig, ax


def prepare_correlation_data(
    processed_data_dict,  # processed_data[model][criteria]
    mcs_stats_df=None,
    mcs_stats_cols=['total_total_rain'],
    time_offset_hours=0,
    radius=2.0,
    variables=None  # Optional: list of variables to include
):
    """
    Prepare data for correlation analysis from processed_data dictionary.
    
    Returns: DataFrame with columns as variables (with pretty labels)
    """
    # Default variable mapping
    VARIABLE_LABELS = {
        # Moisture
        'prw': 'TCWV',
        'rh850': '850 hPa RH',
        'rh500': '500 hPa RH',
        'free_rh': '850-500 hPa RH',
        'q850': '850 hPa Qv',
        'q500': '500 hPa Qv',
        # Dynamics
        'omega850': r'850 hPa $\omega$',
        'omega500': r'500 hPa $\omega$',
        'lShear': 'low-layer shear',
        'dShear': 'deep-layer shear',
        # Predictand
        'total_total_rain': 'total rain'
    }
    
    # If no variables specified, use all except predictand
    if variables is None:
        variables = [k for k in VARIABLE_LABELS.keys() if k != 'total_total_rain']
    
    # Initialize dictionary to collect data
    filtered_data = {}
    
    # Extract environmental variables
    for var in variables:
        if var in processed_data_dict:
            var_df = processed_data_dict[var]
            
            # Filter by radius
            df_filtered = var_df[var_df['radius'] == radius].copy()
            
            # Filter by time_offset_hours
            df_filtered = df_filtered[df_filtered['time_offset_hours'] == time_offset_hours]
            
            # Group by track_id and compute mean (in case of duplicates)
            # This gives us one value per track for each variable
            df_agg = df_filtered.groupby('track_id')['mean'].mean()
            
            # Use pretty label as key
            pretty_label = VARIABLE_LABELS.get(var, var)
            filtered_data[pretty_label] = df_agg
    
    # Create a DataFrame with all variables
    correlation_df = pd.DataFrame(filtered_data)
    
    # Add MCS stats (predictand) if provided
    if mcs_stats_df is not None and len(mcs_stats_cols) > 0:
        # Ensure mcs_stats_cols is a list
        if isinstance(mcs_stats_cols, str):
            mcs_stats_cols = [mcs_stats_cols]
        
        # Extract relevant columns from MCS stats DataFrame
        for col in mcs_stats_cols:
            if col in mcs_stats_df.columns:
                # Map column name to pretty label
                pretty_col = VARIABLE_LABELS.get(col, col)
                
                # Create subset with track_id as index
                mcs_stats_subset = mcs_stats_df[['track_id', col]].copy()
                mcs_stats_subset.set_index('track_id', inplace=True)
                
                # Merge with correlation_df using inner join
                correlation_df = correlation_df.join(mcs_stats_subset.rename(columns={col: pretty_col}), how='inner')
    
    # Drop tracks with any missing values
    correlation_df = correlation_df.dropna()

    # Reorder columns: predictand first, then the rest
    # This ensures the border highlights the correct column
    cols = correlation_df.columns.tolist()
    predictand_cols = [col for col in cols if col in ['total rain']]
    env_cols = [col for col in cols if col not in predictand_cols]
    
    # New order: predictand first, then environmental variables
    new_order = predictand_cols + env_cols
    correlation_df = correlation_df[new_order]
    
    return correlation_df.reset_index(drop=True)


def plot_custom_correlogram(
    processed_data_dict,  # processed_data[model][criteria]
    mcs_stats_df=None,
    mcs_stats_cols=['total_total_rain'],
    time_offset_hours=0,
    radius=2.0,
    variables=None,  # Optional subset
    correlation_method='pearson',  # or 'spearman'
    figsize=(12, 12),
    figname='correlogram.png',
    title='Correlogram',
    alpha_nonsig=0.5,
    p_thresh=0.05,
    **kwargs  # Pass through to custom_correlogram
):
    """
    Create custom correlogram with grouped variables and significance.
    """
    # Prepare data
    df = prepare_correlation_data(
        processed_data_dict,
        mcs_stats_df=mcs_stats_df,
        mcs_stats_cols=mcs_stats_cols,
        time_offset_hours=time_offset_hours,
        radius=radius,
        variables=variables
    )
    
    print(f"Prepared correlation data with {len(df)} samples and {len(df.columns)} variables")
    print(f"Variables: {df.columns.tolist()}")
    
    # Compute correlation matrix
    if correlation_method == 'pearson':
        corr_df = df.corr(method='pearson')
        p_df = pearsonr_pvalues(df)
    elif correlation_method == 'spearman':
        corr_df = df.corr(method='spearman')
        p_df = spearmanr_pvalues(df)
    else:
        raise ValueError(f"Unknown correlation method: {correlation_method}")
    
    # Define variable groups (using pretty labels)
    var_groups = [
        ['total rain'],  # Predictand
        ['TCWV', '850 hPa RH', '500 hPa RH', '850-500 hPa RH', '850 hPa Qv', '500 hPa Qv'],  # Moisture
        [r'850 hPa $\omega$', r'500 hPa $\omega$', 'low-layer shear', 'deep-layer shear'],  # Dynamics
    ]
    
    # Filter var_groups to only include columns that exist in corr_df
    var_groups_filtered = []
    for group in var_groups:
        filtered_group = [var for var in group if var in corr_df.columns]
        if len(filtered_group) > 0:
            var_groups_filtered.append(filtered_group)
    
    group_colors = ['black','teal', 'purple', ]
    group_names = [ 'Predictand','Moisture', 'Dynamics']
    
    # Trim colors and names to match filtered groups
    group_colors = group_colors[:len(var_groups_filtered)]
    group_names = group_names[:len(var_groups_filtered)]
    
    # Determine border_columns (highlight predictand if it exists)
    border_columns = kwargs.pop('border_columns', None)
    if border_columns is None:
        border_columns = 1 if 'total rain' in corr_df.columns else None
    
    # Call custom_correlogram
    fig, ax = custom_correlogram(
        corr_df=corr_df,
        p_df=p_df,
        var_groups=var_groups_filtered,
        group_colors=group_colors,
        group_names=group_names,
        figsize=figsize,
        figname=figname,
        title=title,
        alpha_nonsig=alpha_nonsig,
        p_thresh=p_thresh,
        border_columns=border_columns,
        **kwargs
    )
    
    return fig, ax

def get_common_overlap(data_dict, models, crit='all', var='prw', low_p=10, high_p=90):
    """
    Calculates the intersection of ranges [P_low, P_high] across all models.
    """
    global_min = -np.inf
    global_max = np.inf
    
    ranges = {}
    
    for model in models:
        # --- FIX: Access dictionary dynamically using 'crit' ---
        try:
            df = data_dict[model][crit][var]
        except KeyError:
            print(f"Warning: Data not found for {model} -> {crit} -> {var}")
            return None, None

        if df is None:
            print(f"Warning: DataFrame is None for {model} -> {crit} -> {var}")
            return None, None
        
        # Extract values for the CONTROL variable (e.g., PRW)
        values = df['mean'].values
        
        # Calculate percentiles
        lower = np.percentile(values, low_p)
        upper = np.percentile(values, high_p)
        ranges[model] = (lower, upper)
        
        # Update global intersection
        global_min = max(global_min, lower)
        global_max = min(global_max, upper)
    
    # Check if a valid overlap exists
    if global_min >= global_max:
        print(f"No overlap found! Min of tops ({global_max:.2f}) < Max of bottoms ({global_min:.2f})")
        return None, ranges
        
    return (global_min, global_max), ranges


def plot_rain_vs_omega_regression(data_dict, models, crit='all',
                                  constrain_var='prw', 
                                  manual_prw_limits=None,
                                  omega_var='omega850', 
                                  rain_var='total_total_rain',
                                  radius=2, 
                                  time=0,
                                  normalize=False,
                                  use_quantile_norm=False,
                                  lower_quantile=0.05,
                                  upper_quantile=0.95,
                                  legend_fontsize=10, 
                                  ymin=None, 
                                  ymax=None,MODEL_STYLES=None,
                                  figsize=(10, 8)):
    """
    Plot scatter + linear regression of rain vs omega850 for multiple models.
    
    Similar to plot_mean_rain_vs_binned_omega but uses scatter plot and linear regression
    instead of binned means.
    
    Returns
    -------
    fig : matplotlib figure
    regression_stats : dict
        Dictionary with regression statistics per model:
        {'model': {'slope': float, 'intercept': float, 'r2': float, 'pval': float, 'n': int}}
    """
    from scipy import stats
    import matplotlib.gridspec as gridspec
    from scipy.stats import gaussian_kde

    
    # 1. Determine PRW overlap range
    if manual_prw_limits is None:
        print("Using auto-calculated prw overlap range...")
        prw_min, prw_max = get_common_overlap(data_dict, models, crit, constrain_var, radius, time)
        print(f"PRW overlap range: {prw_min:.2f} - {prw_max:.2f}")
    else:
        prw_min, prw_max = manual_prw_limits
        print(f"Using manual prw range: {prw_min:.2f} - {prw_max:.2f}")
    
    # 2. Collect and prepare data for each model
    all_data_for_models = {}
    model_sample_counts = {}
    model_norm_ranges = {}
    
    for model in models:
        if crit == 'all':
            criteria_list = list(data_dict[model].keys())
        else:
            criteria_list = [crit] if isinstance(crit, str) else crit
        
        model_dfs = []
        for c in criteria_list:
            if c not in data_dict[model]:
                continue
            
            df_c = data_dict[model][c][constrain_var]
            df_x = data_dict[model][c][omega_var]
            
            f_c = df_c[(df_c.radius == radius) & (df_c.time_offset_hours == time)]
            f_x = df_x[(df_x.radius == radius) & (df_x.time_offset_hours == time)]
            
            merged = pd.merge(
                f_c[['track_id', 'mean', rain_var]], 
                f_x[['track_id', 'mean']], 
                on='track_id', 
                suffixes=('_prw', '_omega')
            )
            
            subset = merged[
                (merged['mean_prw'] >= prw_min) & 
                (merged['mean_prw'] <= prw_max)
            ].copy()
            
            subset.rename(columns={'mean_omega': 'mean_x'}, inplace=True)
            model_dfs.append(subset)
        
        if model_dfs:
            combined = pd.concat(model_dfs, ignore_index=True)
            all_data_for_models[model] = combined
            model_sample_counts[model] = len(combined)
    
    # 3. Calculate normalization ranges if needed
    if normalize:
        print("\n--- Normalization Ranges ---")
        for model in models:
            if model not in all_data_for_models:
                continue
            subset = all_data_for_models[model]
            
            if use_quantile_norm:
                rain_min = subset[rain_var].quantile(lower_quantile)
                rain_max = subset[rain_var].quantile(upper_quantile)
                omega_min = subset['mean_x'].quantile(lower_quantile)
                omega_max = subset['mean_x'].quantile(upper_quantile)
                print(f"  {MODEL_STYLES[model]['label']} (quantile {lower_quantile}-{upper_quantile}):")
            else:
                rain_min = subset[rain_var].min()
                rain_max = subset[rain_var].max()
                omega_min = subset['mean_x'].min()
                omega_max = subset['mean_x'].max()
                print(f"  {MODEL_STYLES[model]['label']} (min-max):")
            
            model_norm_ranges[model] = {
                'rain_min': rain_min,
                'rain_max': rain_max,
                'omega_min': omega_min,
                'omega_max': omega_max
            }
            print(f"    Rain [{rain_min:.2f}, {rain_max:.2f}], Omega [{omega_min:.3f}, {omega_max:.3f}]")
    
    # 4. Create figure with gridspec layout
    fig = plt.figure(figsize=figsize)
    gs = gridspec.GridSpec(2, 2, figure=fig, 
                          height_ratios=[1, 4], 
                          width_ratios=[4, 1],
                          hspace=0.05, wspace=0.05)
    
    ax_top = fig.add_subplot(gs[0, 0])    # Omega distribution
    ax_main = fig.add_subplot(gs[1, 0])   # Main scatter plot
    ax_right = fig.add_subplot(gs[1, 1])  # Rain distribution
    
    # 5. Process each model, calculate regression, and plot
    regression_stats = {}
    all_omega_data = []
    all_rain_data = []
    
    for model in models:
        if model not in all_data_for_models:
            continue
        
        subset = all_data_for_models[model].copy()
        
        # Apply normalization if requested
        if normalize:
            ranges = model_norm_ranges[model]
            
            if use_quantile_norm:
                # Normalize rain
                rain_min_norm = ranges['rain_min']
                rain_max_norm = ranges['rain_max']
                clipped_rain = np.clip(subset[rain_var], rain_min_norm, rain_max_norm)
                subset[rain_var] = (clipped_rain - rain_min_norm) / (rain_max_norm - rain_min_norm)
                
                # Normalize omega (reversed)
                omega_min_norm = ranges['omega_min']
                omega_max_norm = ranges['omega_max']
                clipped_omega = np.clip(subset['mean_x'], omega_min_norm, omega_max_norm)
                subset['mean_x'] = 1 - ((clipped_omega - omega_min_norm) / (omega_max_norm - omega_min_norm))
            else:
                # Min-max normalization
                if ranges['rain_max'] > ranges['rain_min']:
                    subset[rain_var] = ((subset[rain_var] - ranges['rain_min']) / 
                                       (ranges['rain_max'] - ranges['rain_min']))
                if ranges['omega_max'] > ranges['omega_min']:
                    subset['mean_x'] = 1 - ((subset['mean_x'] - ranges['omega_min']) / 
                                           (ranges['omega_max'] - ranges['omega_min']))
        
        # Get data for regression and plotting
        omega_vals = subset['mean_x'].values
        rain_vals = subset[rain_var].values
        
        # Remove NaN values
        valid_mask = ~(np.isnan(omega_vals) | np.isnan(rain_vals))
        omega_vals_clean = omega_vals[valid_mask]
        rain_vals_clean = rain_vals[valid_mask]
        
        if len(omega_vals_clean) < 3:
            print(f"Warning: {model} has insufficient data for regression")
            continue
        
        # Calculate linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(omega_vals_clean, rain_vals_clean)
        r2 = r_value ** 2
        
        regression_stats[model] = {
            'slope': slope,
            'intercept': intercept,
            'r2': r2,
            'pval': p_value,
            'std_err': std_err,
            'n': len(omega_vals_clean)
        }
        
        # Collect data for distributions
        all_omega_data.extend(omega_vals_clean)
        all_rain_data.extend(rain_vals_clean)
        
        # Plot scatter points
        ax_main.scatter(omega_vals_clean, rain_vals_clean,
                       color=MODEL_STYLES[model]['color'],
                       alpha=0.5,
                       s=20,
                       label=MODEL_STYLES[model]['label'],
                       edgecolors='none')
        
        # Plot regression line
        omega_range = np.array([omega_vals_clean.min(), omega_vals_clean.max()])
        regression_line = slope * omega_range + intercept
        ax_main.plot(omega_range, regression_line,
                    color=MODEL_STYLES[model]['color'],
                    linewidth=MODEL_STYLES[model].get('lw', 2.5),
                    linestyle='--',
                    alpha=0.8)
        
        # Plot omega distribution (top)
        model_omega_df = pd.DataFrame({'mean_x': omega_vals_clean, 'model': model})
        from scipy.stats import gaussian_kde
        if len(omega_vals_clean) > 1:
            kde = gaussian_kde(omega_vals_clean)
            omega_plot = np.linspace(omega_vals_clean.min(), omega_vals_clean.max(), 200)
            density = kde(omega_plot)
            ax_top.plot(omega_plot, density,
                       color=MODEL_STYLES[model]['color'],
                       linewidth=MODEL_STYLES[model].get('lw', 2.5),
                       label=MODEL_STYLES[model]['label'])
            # ax_top.fill_between(omega_plot, density, alpha=0.3,
            #                    color=MODEL_STYLES[model]['color'])
        
        # Plot rain distribution (right)
        if len(rain_vals_clean) > 1:
            kde = gaussian_kde(rain_vals_clean)
            rain_plot = np.linspace(rain_vals_clean.min(), rain_vals_clean.max(), 200)
            density = kde(rain_plot)
            ax_right.plot(density, rain_plot,
                         color=MODEL_STYLES[model]['color'],
                         linewidth=MODEL_STYLES[model].get('lw', 2.5))
            # ax_right.fill_betweenx(rain_plot, density, alpha=0.3,
            #                        color=MODEL_STYLES[model]['color'])
    
    # 6. Configure axes
    # Main plot
    if normalize:
        if use_quantile_norm:
            norm_label = f"(Quantile norm {lower_quantile:.0%}-{upper_quantile:.0%})"
        else:
            norm_label = "(Min-max norm)"
        ax_main.set_xlabel(f'Normalized Omega850\n{norm_label}\n(1=strongest ascent, 0=weakest)', fontsize=12)
        ax_main.set_ylabel(f'Normalized {rain_var}\n{norm_label}', fontsize=12)
        if not use_quantile_norm:
            ax_main.axvline(0.5, color='gray', linestyle='--', alpha=0.3, linewidth=1)
    else:
        ax_main.set_xlabel(f'{omega_var} (Pa/s)', fontsize=12)
        ax_main.set_ylabel(f'{rain_var}', fontsize=12)
        ax_main.axvline(0, color='gray', linestyle='--', alpha=0.3, linewidth=1, label='Zero omega')
    
    # Create legend with regression statistics
    legend_handles = []
    legend_labels = []
    
    for model in models:
        if model in regression_stats:
            stats_dict = regression_stats[model]
            
            # Format p-value
            if stats_dict['pval'] < 0.001:
                p_str = "p<0.001"
            elif stats_dict['pval'] < 0.01:
                p_str = f"p<0.01"
            else:
                p_str = f"p={stats_dict['pval']:.3f}"
            
            # Format slope with appropriate units
            if normalize:
                slope_str = f"{stats_dict['slope']:.3f}"
                units = ""
            else:
                slope_str = f"{stats_dict['slope']:.3f}"
                units = " mm·s/Pa"
            
            # Create label with all statistics
            label = (f"{MODEL_STYLES[model]['label']} (N={stats_dict['n']})\n"
                    # f"  slope={slope_str}{units}, R²={stats_dict['r2']:.2f}, {p_str}")
                     f"  slope={slope_str}{units}, R²={stats_dict['r2']:.2f}")
            
            # Create a dummy handle with the model color
            from matplotlib.lines import Line2D
            handle = Line2D([0], [0], color=MODEL_STYLES[model]['color'], 
                          linewidth=MODEL_STYLES[model].get('lw', 2.5),
                          linestyle='--', marker='o', markersize=6, alpha=0.7)
            
            legend_handles.append(handle)
            legend_labels.append(label)
    
    ax_main.legend(legend_handles, legend_labels, fontsize=legend_fontsize, 
                  loc='best', framealpha=0.9)
    ax_main.grid(True, alpha=0.3)
    
    if ymin is not None or ymax is not None:
        ax_main.set_ylim(ymin, ymax)
    
    # Top omega distribution
    ax_top.set_ylabel('Density', fontsize=10)
    ax_top.tick_params(labelbottom=False)
    ax_top.grid(True, alpha=0.3, axis='y')
    if normalize:
        ax_top.set_title(f'Scatter + Regression: {rain_var} vs {omega_var}\nPRW: {prw_min:.1f}-{prw_max:.1f} mm | Normalized', 
                        fontsize=12)
    else:
        ax_top.set_title(f'Scatter + Regression: {rain_var} vs {omega_var}\nPRW: {prw_min:.1f}-{prw_max:.1f} mm', 
                        fontsize=12)
    
    # Right rain distribution
    ax_right.set_xlabel('Density', fontsize=10)
    ax_right.tick_params(labelleft=False)
    ax_right.grid(True, alpha=0.3, axis='x')
    ax_right.sharey(ax_main)
    
    # plt.tight_layout()
    
    # 7. Print regression statistics
    # print("\n" + "="*80)
    # print("LINEAR REGRESSION STATISTICS")
    # print("="*80)
    # for model in models:
    #     if model in regression_stats:
    #         stats_dict = regression_stats[model]
    #         print(f"\n{MODEL_STYLES[model]['label']} (N={stats_dict['n']}):")
    #         print(f"  Slope:     {stats_dict['slope']:8.4f}")
    #         print(f"  Intercept: {stats_dict['intercept']:8.4f}")
    #         print(f"  R²:        {stats_dict['r2']:8.4f}")
    #         print(f"  p-value:   {stats_dict['pval']:8.2e}")
    #         print(f"  Std Error: {stats_dict['std_err']:8.4f}")
    
    return fig, regression_stats


def plot_conditional_rain_distribution(data_dict, models, crit='all',
                                       binned_var='omega850',
                                       bins=None,
                                       n_bins=20, # used when normalized = True (e.g, 10 for deciles)
                                       constrain_var='prw', 
                                       manual_constrain_limits=None,
                                       rain_var='total_total_rain',
                                       stat='mean',MODEL_STYLES=None,
                                       error_type='iqr',
                                       normalize=False, 
                                       normalize_y=True,
                                       use_quantile_norm=False,
                                       lower_quantile=0.05,
                                       upper_quantile=0.95,
                                       radius=2, 
                                       time=0,
                                       min_samples_per_bin=10,
                                       show_bin_separators=True,  
                                       xaxis_multiplier=1,  # multiply bin edges for display
                                       xaxis_units='',      # units to show in label
                                       legend_fontsize=10, 
                                       ymin=None, 
                                       ymax=None,
                                       xmin=None,
                                       xmax=None,rot=0,
                                       legend_loc='best',
                                       figsize=(10, 8)):
    """
    Plot conditional rain distribution as scatter plot with error bars.
    
    Shows mean/median rain for bins of a specified variable, constrained by another variable.
    Uses scatter plot with error bars instead of line plot.
    
    Parameters
    ----------
    data_dict : dict
        Nested dictionary with structure: data_dict[model][criterion][variable]
    models : list of str
        List of model names to plot
    crit : str or list, default='all'
        Criterion/criteria to use. If 'all', uses all available criteria.
    binned_var : str, default='omega850'
        Variable to bin (x-axis). E.g., 'omega850', 'prw', 'shf', etc.
    bins : array-like
        Bin edges for the binned variable. E.g., [-0.5, -0.2, -0.1, 0, 0.1]
    constrain_var : str, default='prw'
        Variable to constrain the data (e.g., 'prw')
    manual_constrain_limits : tuple or None, default=None
        Manual limits for constraint variable (min, max).
        If None, uses get_common_overlap() to find overlap.
    rain_var : str, default='total_total_rain'
        Rain variable to plot on y-axis
    stat : str, default='mean'
        Statistic to calculate: 'mean' or 'median'
    error_type : str, default='iqr'
        Type of error bars:
        - 'iqr': Inter-quartile range
        - 'ci95': 95% confidence interval for mean/median
        
    radius : int, default=2
        Radius index for spatial averaging
    time : int, default=0
        Time offset in hours
    min_samples_per_bin : int, default=10
        Minimum samples required per bin to plot
    legend_fontsize : int, default=10
        Font size for legend
    ymin, ymax : float, optional
        Y-axis limits
    xmin, xmax : float, optional
        X-axis limits
    figsize : tuple, default=(10, 8)
        Figure size (width, height)
    
    Returns
    -------
    fig : matplotlib figure
    final_df : pandas DataFrame
        Binned data with statistics
    """
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import seaborn as sns
    import numpy as np
    import pandas as pd
    from scipy import stats as scipy_stats
    
    # Validate inputs
    if not normalize and bins is None:
        raise ValueError("bins parameter is required. Provide bin edges as array-like.")
    
    if bins is not None:
        bins = np.array(bins)
    
    if stat not in ['mean', 'median']:
        raise ValueError("stat must be 'mean' or 'median'")
    
    if error_type not in ['iqr', 'ci95']:
        raise ValueError("error_type must be 'iqr' or 'ci95'")
    
    # 1. Determine constraint variable range
    if manual_constrain_limits is None:
        print(f"Using auto-calculated {constrain_var} overlap range...")
        constrain_limits, _ = get_common_overlap(data_dict, models, crit=crit, var=constrain_var)
        print(f"{constrain_var} overlap range: {constrain_limits[0]:.2f} - {constrain_limits[1]:.2f}")
    else:
        constrain_limits = manual_constrain_limits
        print(f"Using manual {constrain_var} range: {constrain_limits[0]:.2f} - {constrain_limits[1]:.2f}")
    
    # constrain_limits = (constrain_min, constrain_max)
    
    # 2. Collect data for each model
    all_data_for_models = {}
    model_sample_counts = {}
    
    for model in models:
        if crit == 'all':
            criteria_list = list(data_dict[model].keys())
        else:
            criteria_list = [crit] if isinstance(crit, str) else crit
        
        model_dfs = []
        for c in criteria_list:
            if c not in data_dict[model]:
                continue
            
            # Get constraint variable data
            df_constrain = data_dict[model][c][constrain_var]
            # Get binned variable data
            df_binned = data_dict[model][c][binned_var]
            
            # Filter by radius and time
            f_constrain = df_constrain[(df_constrain.radius == radius) & 
                                       (df_constrain.time_offset_hours == time)]
            f_binned = df_binned[(df_binned.radius == radius) & 
                                 (df_binned.time_offset_hours == time)]
            
            # Merge on track_id
            merged = pd.merge(
                f_constrain[['track_id', 'mean', rain_var]], 
                f_binned[['track_id', 'mean']], 
                on='track_id', 
                suffixes=('_constrain', '_binned')
            )
            
            # Apply constraint
            subset = merged[
                (merged['mean_constrain'] >= constrain_limits[0]) & 
                (merged['mean_constrain'] <= constrain_limits[1])
            ].copy()
            
            subset.rename(columns={'mean_binned': 'binned_value'}, inplace=True)
            model_dfs.append(subset)
        
        if model_dfs:
            combined = pd.concat(model_dfs, ignore_index=True)
            all_data_for_models[model] = combined
            model_sample_counts[model] = len(combined)
            print(f"{MODEL_STYLES[model]['label']}: {len(combined)} samples in {constrain_var} range")
    
    if not all_data_for_models:
        print("No models had data in the specified range.")
        return None, None
    
    # 3. Bin data and calculate statistics
    processed_dfs = []
    all_binned_data = []  # For distribution
    all_rain_data = []    # For distribution
    
    for model in models:
        if model not in all_data_for_models:
            continue
        
        subset = all_data_for_models[model].copy()

        # Apply normalization if requested
        if normalize:
            if use_quantile_norm:
                # Get quantiles for binned variable
                q_low_x = subset['binned_value'].quantile(lower_quantile)
                q_high_x = subset['binned_value'].quantile(upper_quantile)
                
                # Clip and normalize binned variable
                clipped_x = np.clip(subset['binned_value'], q_low_x, q_high_x)
                subset['binned_value'] = (clipped_x - q_low_x) / (q_high_x - q_low_x)
                
                # Optionally normalize rain variable
                if normalize_y:
                    q_low_y = subset[rain_var].quantile(lower_quantile)
                    q_high_y = subset[rain_var].quantile(upper_quantile)
                    clipped_y = np.clip(subset[rain_var], q_low_y, q_high_y)
                    subset[rain_var] = (clipped_y - q_low_y) / (q_high_y - q_low_y)
            else:
                # Min-max normalization
                x_min, x_max = subset['binned_value'].min(), subset['binned_value'].max()
                
                if x_max > x_min:
                    subset['binned_value'] = (subset['binned_value'] - x_min) / (x_max - x_min)
                
                # Optionally normalize rain variable
                if normalize_y:
                    y_min, y_max = subset[rain_var].min(), subset[rain_var].max()
                    if y_max > y_min:
                        subset[rain_var] = (subset[rain_var] - y_min) / (y_max - y_min)
        
        # Store data for distribution plots
        binned_data_model = subset[['binned_value']].copy()
        binned_data_model['Model'] = model
        binned_data_model['Model_Label'] = MODEL_STYLES[model]['label']
        all_binned_data.append(binned_data_model)
        
        rain_data_model = subset[[rain_var]].copy()
        rain_data_model['Model'] = model
        rain_data_model['Model_Label'] = MODEL_STYLES[model]['label']
        all_rain_data.append(rain_data_model)
        
        # Create bins
        # binned_categories = pd.cut(subset['binned_value'], bins=bins, include_lowest=True, duplicates='drop')
        if normalize:
            # Use quantile bins for normalized data
            binned_categories = pd.qcut(subset['binned_value'], q=n_bins, labels=False, duplicates='drop')
        else:
            # Use user-provided bins for raw data
            binned_categories = pd.cut(subset['binned_value'], bins=bins, include_lowest=True, duplicates='drop')
        
        # Group by bin and calculate statistics
        grouped = subset.groupby(binned_categories, observed=False)[rain_var]
        
        # Calculate central tendency
        if stat == 'mean':
            central_values = grouped.mean()
        else:  # median
            central_values = grouped.median()
        
        # Calculate error bars
        counts = grouped.count()
        
        if error_type == 'iqr':
            # Inter-quartile range (25th to 75th percentile)
            q25 = grouped.quantile(0.25)
            q75 = grouped.quantile(0.75)
            error_lower = central_values - q25
            error_upper = q75 - central_values
        elif error_type == 'ci95':
            # 95% confidence interval
            if stat == 'mean':
                # CI for mean: mean ± t * (std / sqrt(n))
                std_vals = grouped.std()
                from scipy.stats import t
                ci_lower = []
                ci_upper = []
                for bin_cat in central_values.index:
                    n = counts[bin_cat]
                    if n >= 2:
                        s = std_vals[bin_cat]
                        m = central_values[bin_cat]
                        t_val = t.ppf(0.975, n-1)
                        margin = t_val * s / np.sqrt(n)
                        ci_lower.append(m - margin)
                        ci_upper.append(m + margin)
                    else:
                        ci_lower.append(np.nan)
                        ci_upper.append(np.nan)
                error_lower = central_values - np.array(ci_lower)
                error_upper = np.array(ci_upper) - central_values
            else:  # median - use bootstrap approximation
                q25 = grouped.quantile(0.25)
                q75 = grouped.quantile(0.75)
                error_lower = central_values - q25
                error_upper = q75 - central_values
        
        # Create results dataframe
        agg_results = pd.DataFrame({
            stat: central_values,
            'count': counts,
            'error_lower': error_lower,
            'error_upper': error_upper
        })
        
        # Filter bins with insufficient samples
        agg_results = agg_results[agg_results['count'] >= min_samples_per_bin].copy()
        
        if agg_results.empty:
            print(f"Warning: {model} has no bins with >= {min_samples_per_bin} samples")
            continue
        
        # Calculate bin centers differently for normalized vs raw data
        if normalize:
            # For normalized data: bins are integer labels, calculate centers in normalized space
            agg_results['bin_center'] = agg_results.index.map(lambda x: (x + 0.5) / n_bins if pd.notna(x) else np.nan).astype(float)
        else:
            # For raw data: bins are Interval objects, use midpoint
            agg_results['bin_center'] = agg_results.index.map(lambda x: x.mid if pd.notna(x) else np.nan).astype(float)
            
        # Add metadata
        agg_results['Model'] = model
        agg_results['Model_Label'] = MODEL_STYLES[model]['label']
        
        # Reset index
        agg_results = agg_results.reset_index(drop=True)
        
        processed_dfs.append(agg_results)
    
    if not processed_dfs:
        print("No models had sufficient data in bins.")
        return None, None
    
    final_df = pd.concat(processed_dfs, ignore_index=True)
    
    # Combine data for distributions
    all_binned_combined = pd.concat(all_binned_data, ignore_index=True)
    all_rain_combined = pd.concat(all_rain_data, ignore_index=True)
    
    # 4. Create figure with joint plot layout
    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(2, 2, width_ratios=[4, 1], height_ratios=[1, 4],
                          hspace=0.1, wspace=0.05)
    
    ax_main = fig.add_subplot(gs[1, 0])     # Main scatter plot
    ax_top = fig.add_subplot(gs[0, 0], sharex=ax_main)  # Binned var distribution
    ax_right = fig.add_subplot(gs[1, 1], sharey=ax_main)  # Rain distribution
    
    # 5. Plot TOP: Binned variable distribution (KDE)
    for model in models:
        if model not in all_data_for_models:
            continue
        model_binned = all_binned_combined[all_binned_combined['Model'] == model]
        
        if len(model_binned) > 0:
            sns.kdeplot(
                data=model_binned,
                x='binned_value',
                color=MODEL_STYLES[model]['color'],
                linewidth=MODEL_STYLES[model].get('lw', 2.5),
                ax=ax_top,
                label=MODEL_STYLES[model]['label'],
                fill=False
            )
    
    ax_top.set_xlabel('')
    ax_top.set_ylabel('Density', fontsize=10)
    ax_top.tick_params(axis='x', labelbottom=False)
    ax_top.grid(True, linestyle=':', alpha=0.6, axis='x')
    ax_top.legend().set_visible(False)
    ax_top.set_title(f'{binned_var} Distribution', fontsize=11)
    
    # 6. Plot MAIN: Scatter with error bars and horizontal offsets
    
    # Calculate fixed offset for each model
    n_models = len([m for m in models if m in all_data_for_models])
    if normalize:
        bin_width = 1.0 / n_bins  # Width in normalized space
    else:
        bin_width = np.diff(bins).min()  # Use minimum bin width for consistent spacing
    offset_width = 0.65 * bin_width  # Total width for all models (15% of bin width)
    
    # Create offsets centered around zero
    if n_models > 1:
        model_offsets = np.linspace(-offset_width/2, offset_width/2, n_models)
    else:
        model_offsets = [0]
    
    # Map each model to its offset
    model_to_offset = {}
    offset_idx = 0
    for model in models:
        if model in all_data_for_models:
            model_to_offset[model] = model_offsets[offset_idx]
            offset_idx += 1
    
    # Plot each model with its offset
    for model in models:
        if model not in all_data_for_models:
            continue
        
        model_data = final_df[final_df['Model'] == model]
        if model_data.empty:
            continue
        
        model_label = MODEL_STYLES[model]['label']
        n_samples = model_sample_counts[model]
        label_with_count = f"{model_label} (N={n_samples})"
        
        # Apply horizontal offset
        x_positions = model_data['bin_center'].values + model_to_offset[model]
        
        # Plot error bars
        ax_main.errorbar(
            x_positions,
            model_data[stat],
            yerr=[model_data['error_lower'], model_data['error_upper']],
            fmt='o',
            color=MODEL_STYLES[model]['color'],
            markersize=8,
            capsize=0,
            capthick=2,
            elinewidth=2,
            label=label_with_count,
            alpha=0.8
        )
    
    # Create bin range labels with unit conversion
    bin_labels = []
    bin_centers = []
    
    if normalize:
        # For normalized data: show bin center numbers
        for i in range(n_bins):
            bin_center = (i + 0.5) / n_bins  # Normalized center
            bin_centers.append(bin_center)
            bin_labels.append(f"{bin_center:.1f}")
            
    else:
        # For raw data: show bin center values with unit conversion
        for i in range(len(bins) - 1):
            bin_center = (bins[i] + bins[i+1]) / 2
            bin_centers.append(bin_center)
            
            # Apply multiplier for display (e.g., kg/kg to g/kg)
            display_center = bin_center * xaxis_multiplier
            
            # Format with appropriate precision based on bin width
            bin_width_display = (bins[i+1] - bins[i]) * xaxis_multiplier
            if bin_width_display < 1:
                bin_labels.append(f"{display_center:.1f}")
            elif bin_width_display < 10:
                bin_labels.append(f"{display_center:.1f}")
            else:
                bin_labels.append(f"{display_center:.0f}")
    
    # Scale y-axis by dividing by 10000
    from matplotlib.ticker import FuncFormatter
    
    if not normalize_y:
        def format_yticks(value, pos):
            return f'{value/10000:.0f}'
    
        ax_main.yaxis.set_major_formatter(FuncFormatter(format_yticks))
    
    # Set x-ticks at bin centers with range labels
    ax_main.set_xticks(bin_centers)
    ax_main.set_xticklabels(bin_labels, rotation=rot, ha='right',)
    
    # Add vertical separators at bin edges if requested
    if show_bin_separators:
        for bin_edge in bins:
            ax_main.axvline(bin_edge, color='gray', linestyle=':', alpha=0.3, linewidth=1, zorder=0)
    
    # Set labels and formatting
    if normalize:
        norm_label = f"Quantile {lower_quantile:.0%}-{upper_quantile:.0%}" if use_quantile_norm else "Min-Max"
        ax_main.set_xlabel(f"Normalized {binned_var}\n({norm_label})", fontsize=12)
    else:
        if xaxis_units:
            ax_main.set_xlabel(f"{binned_var} ({xaxis_units})", fontsize=12)
        else:
            ax_main.set_xlabel(f"{binned_var} (bin ranges)", fontsize=12)
        # ax_main.set_ylabel(f"{stat.capitalize()} {rain_var} (mm)", fontsize=12)
        # ax_main.set_ylabel(f"{stat.capitalize()} total MCS precipitation \n (mm, ×10⁴)", fontsize=12)

    if normalize and normalize_y:
        norm_label = f"Quantile {lower_quantile:.0%}-{upper_quantile:.0%}" if use_quantile_norm else "Min-Max"
        ax_main.set_ylabel(f"Normalized {stat} total MCS precipitation \n({norm_label})", fontsize=12)
    else:
        # ax_main.set_yscale('log')
        ax_main.set_ylabel(f"{stat.capitalize()} total MCS precipitation \n (mm, ×10⁴)", fontsize=12)
    
    # Apply custom limits
    if ymin is not None or ymax is not None:
        current_ylim = ax_main.get_ylim()
        new_ymin = ymin if ymin is not None else current_ylim[0]
        new_ymax = ymax if ymax is not None else current_ylim[1]
        ax_main.set_ylim(new_ymin, new_ymax)
    
    if xmin is not None or xmax is not None:
        current_xlim = ax_main.get_xlim()
        new_xmin = xmin if xmin is not None else current_xlim[0]
        new_xmax = xmax if xmax is not None else current_xlim[1]
        ax_main.set_xlim(new_xmin, new_xmax)
    else:
         # Auto-set x limits to show full bins with padding
        if normalize:
            ax_main.set_xlim(-bin_width*0.2, 1 + bin_width*0.2)  # 0 to 1 for normalized
        else:
            ax_main.set_xlim(bins[0] - bin_width*0.2, bins[-1] + bin_width*0.2)
    
    error_label = "IQR (25-75%)" if error_type == 'iqr' else "95% CI"
    ax_main.legend(fontsize=legend_fontsize, frameon=False, loc=legend_loc, ncol=2,
                  title=f"Error bars: {error_label}")
    ax_main.grid(True, linestyle=':', alpha=0.6)

    
    
    # 7. Plot RIGHT: Rain distribution (KDE)
    for model in models:
        if model not in all_data_for_models:
            continue
        model_rain = all_rain_combined[all_rain_combined['Model'] == model]
        
        if len(model_rain) > 0:
            sns.kdeplot(
                data=model_rain,
                y=rain_var,
                color=MODEL_STYLES[model]['color'],
                linewidth=MODEL_STYLES[model].get('lw', 2.5),
                ax=ax_right,
                label=MODEL_STYLES[model]['label']
            )
    
    ax_right.set_ylabel('')
    ax_right.set_xlabel('Density', fontsize=10)
    ax_right.tick_params(axis='y', labelleft=False)
    ax_right.grid(True, linestyle=':', alpha=0.6, axis='y')
    ax_right.legend().set_visible(False)
    ax_right.set_title('MCS Precip. Dist.', fontsize=10)
    
    # Overall title
    fig.suptitle(f"{stat.capitalize()} {rain_var} vs {binned_var} "
                f"({constrain_var}: {constrain_limits[0]:.1f}-{constrain_limits[1]:.1f})", 
                fontsize=12, y=0.98)
    
    plt.tight_layout()
    
    return fig, final_df