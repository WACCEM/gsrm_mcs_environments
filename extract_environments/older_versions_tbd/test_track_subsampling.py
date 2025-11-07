#!/usr/bin/env python
"""
Test script to verify track subsampling logic for model time frequency matching.

This script tests the subsample_tracks_by_frequency function to ensure it correctly
reduces track time steps to match model output frequency.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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

def create_test_tracks():
    """Create synthetic track data for testing."""
    
    # Create Track 1: 24 hourly time steps
    track1_start = datetime(2020, 1, 1, 0, 0, 0)
    track1_times = [track1_start + timedelta(hours=i) for i in range(24)]
    
    track1_df = pd.DataFrame({
        'tracks': [1] * 24,
        'times': list(range(24)),
        'base_time': track1_times,
        'meanlon': [100.0 + i*0.1 for i in range(24)],
        'meanlat': [10.0 + i*0.1 for i in range(24)]
    })
    
    # Create Track 2: 18 hourly time steps
    track2_start = datetime(2020, 1, 2, 6, 0, 0)
    track2_times = [track2_start + timedelta(hours=i) for i in range(18)]
    
    track2_df = pd.DataFrame({
        'tracks': [2] * 18,
        'times': list(range(18)),
        'base_time': track2_times,
        'meanlon': [105.0 + i*0.1 for i in range(18)],
        'meanlat': [15.0 + i*0.1 for i in range(18)]
    })
    
    # Combine tracks
    all_tracks = pd.concat([track1_df, track2_df], ignore_index=True)
    
    return all_tracks

def test_subsampling():
    """Test the subsampling function with different frequencies."""
    
    print("="*60)
    print("Testing Track Subsampling")
    print("="*60)
    
    # Create test data
    print("\nCreating test tracks...")
    df = create_test_tracks()
    print(f"Created {len(df)} total time steps:")
    print(f"  - Track 1: 24 hourly steps")
    print(f"  - Track 2: 18 hourly steps")
    
    # Test 1: 3-hourly subsampling
    print("\n" + "="*60)
    print("TEST 1: 3-hourly subsampling (like UM/SCREAM)")
    print("="*60)
    df_3h = subsample_tracks_by_frequency(df.copy(), '3H')
    
    # Verify results
    track1_3h = df_3h[df_3h['tracks'] == 1]
    track2_3h = df_3h[df_3h['tracks'] == 2]
    
    print(f"\nTrack 1: {len(track1_3h)} time steps (expected: 8)")
    print(f"  Time indices: {sorted(track1_3h['times'].tolist())}")
    assert len(track1_3h) == 8, f"Expected 8 steps, got {len(track1_3h)}"
    
    print(f"\nTrack 2: {len(track2_3h)} time steps (expected: 6)")
    print(f"  Time indices: {sorted(track2_3h['times'].tolist())}")
    assert len(track2_3h) == 6, f"Expected 6 steps, got {len(track2_3h)}"
    
    # Test 2: 6-hourly subsampling
    print("\n" + "="*60)
    print("TEST 2: 6-hourly subsampling (like ICON)")
    print("="*60)
    df_6h = subsample_tracks_by_frequency(df.copy(), '6H')
    
    # Verify results
    track1_6h = df_6h[df_6h['tracks'] == 1]
    track2_6h = df_6h[df_6h['tracks'] == 2]
    
    print(f"\nTrack 1: {len(track1_6h)} time steps (expected: 4)")
    print(f"  Time indices: {sorted(track1_6h['times'].tolist())}")
    assert len(track1_6h) == 4, f"Expected 4 steps, got {len(track1_6h)}"
    
    print(f"\nTrack 2: {len(track2_6h)} time steps (expected: 3)")
    print(f"  Time indices: {sorted(track2_6h['times'].tolist())}")
    assert len(track2_6h) == 3, f"Expected 3 steps, got {len(track2_6h)}"
    
    # Test 3: 1-hourly (should keep all)
    print("\n" + "="*60)
    print("TEST 3: 1-hourly subsampling (no reduction)")
    print("="*60)
    df_1h = subsample_tracks_by_frequency(df.copy(), '1H')
    
    assert len(df_1h) == len(df), f"Expected {len(df)} steps, got {len(df_1h)}"
    print("\n✓ All time steps preserved (as expected)")
    
    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60)
    
    # Show example of what gets kept
    print("\nExample: Track 1 with 3H frequency")
    track1_example = df[df['tracks'] == 1][['times', 'base_time']].head(12)
    print("\nOriginal (first 12 hours):")
    print(track1_example.to_string(index=False))
    
    track1_3h_example = df_3h[df_3h['tracks'] == 1][['times', 'base_time']].head(4)
    print("\nAfter 3H subsampling (kept):")
    print(track1_3h_example.to_string(index=False))

if __name__ == '__main__':
    test_subsampling()
