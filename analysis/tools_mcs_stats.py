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
        'ERA5': 'k',
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
            df_filtered = df[
                (df['time_offset_hours'] >= time_range[0]) &
                (df['time_offset_hours'] <= time_range[1]) &
                (df['radius'] == radius)
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
               bbox_to_anchor=(0.5, -0.01), ncol=min(len(legend_elements), 5), fontsize=fontsize)
    
    fig.tight_layout(rect=[0, 0.05, 1, 0.98])

    return fig


def plot_correlation_matrix(var_dfs_dict, time_window=(-6, 0), radius=2.0,
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
    
    # Drop tracks with any missing values
    correlation_df = correlation_df.dropna()
    
    # Compute correlation matrix
    corr_matrix = correlation_df.corr()
    
    # Create mask for upper triangle if requested
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