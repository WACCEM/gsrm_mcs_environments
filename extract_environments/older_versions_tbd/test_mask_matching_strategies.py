"""
Diagnostic test: Compare different approaches for track-mask matching

The mask file is TOO LARGE to load into memory. We need streaming approaches:

1. Sequential streaming: Read one time slice at a time, process immediately
2. Small batch streaming: Read N time slices, process, discard, repeat
3. Chunked dask: Use dask's chunking without loading to memory

The key is to NEVER load the full mask or large subsets into memory.

Author: Laura Paccini
Date: November 2025
"""

import numpy as np
import pandas as pd
import xarray as xr
import time
import sys


def test_sequential_streaming(track_df, mask_data, num_samples=100):
    """
    Test 1: Sequential streaming - read one time slice at a time
    
    Strategy: For each track-time, read that single mask slice, process, discard
    NO LOADING INTO MEMORY - pure streaming
    """
    print("\n" + "="*60)
    print("TEST 1: Sequential Streaming (Minimal Memory)")
    print("="*60)
    
    sample_df = track_df.sample(min(num_samples, len(track_df)))
    
    print(f"Sample size: {len(sample_df)} track-time combinations")
    
    start_time = time.time()
    results = []
    
    for idx, row in sample_df.iterrows():
        track_id = int(row['track_id'])
        track_time = pd.Timestamp(row['base_time'])
        
        try:
            # Use sel with method='nearest' instead of loading all times
            # This is more memory-efficient
            mask_slice = mask_data.sel(time=track_time, method='nearest').values
            
            # Find cells for this track
            cells = np.where(mask_slice == track_id)[0]
            results.append(len(cells))
            
        except Exception as e:
            results.append(0)
    
    elapsed = time.time() - start_time
    
    print(f"Total time: {elapsed:.3f} seconds")
    print(f"Average per track-time: {elapsed/len(sample_df)*1000:.2f} ms")
    print(f"Found cells for {len([r for r in results if r > 0])} tracks")
    
    return elapsed / len(sample_df)


def test_small_batch_streaming(track_df, mask_data, num_samples=100, batch_size=10):
    """
    Test 2: Small batch streaming - read N unique times, process, discard
    
    Strategy: Group by unique times, load small batches, process, discard
    """
    print("\n" + "="*60)
    print(f"TEST 2: Small Batch Streaming (batch_size={batch_size})")
    print("="*60)
    
    sample_df = track_df.sample(min(num_samples, len(track_df)))
    
    # Get unique times
    unique_times = sorted(sample_df['base_time'].unique())
    print(f"Sample size: {len(sample_df)} track-time combinations")
    print(f"Unique times: {len(unique_times)}")
    
    # Group tracks by time
    time_to_tracks = {}
    for _, row in sample_df.iterrows():
        track_time = pd.Timestamp(row['base_time'])
        if track_time not in time_to_tracks:
            time_to_tracks[track_time] = []
        time_to_tracks[track_time].append(int(row['track_id']))
    
    start_time = time.time()
    results = []
    
    # Process unique times in small batches
    for batch_start in range(0, len(unique_times), batch_size):
        batch_end = min(batch_start + batch_size, len(unique_times))
        batch_times = unique_times[batch_start:batch_end]
        
        try:
            # Use sel with method='nearest' for this batch
            mask_batch = mask_data.sel(time=batch_times, method='nearest').values
            
            # Process each time in batch
            for local_idx, track_time in enumerate(batch_times):
                mask_at_time = mask_batch[local_idx]
                
                for track_id in time_to_tracks[track_time]:
                    cells = np.where(mask_at_time == track_id)[0]
                    results.append(len(cells))
            
        except Exception as e:
            print(f"Error in batch {batch_start}: {e}")
            continue
    
    elapsed = time.time() - start_time
    
    print(f"Total time: {elapsed:.3f} seconds")
    print(f"Average per track-time: {elapsed/len(sample_df)*1000:.2f} ms")
    print(f"Found cells for {len([r for r in results if r > 0])} tracks")
    
    return elapsed / len(sample_df)


def test_grouped_by_time(track_df, mask_data, num_samples=100):
    """
    Test 3: Group tracks by time, process one time at a time
    
    Strategy: For each unique time, load once, process all tracks at that time
    """
    print("\n" + "="*60)
    print("TEST 3: Grouped by Time (Optimal Reuse)")
    print("="*60)
    
    sample_df = track_df.sample(min(num_samples, len(track_df)))
    
    # Get unique times
    unique_times = sorted(sample_df['base_time'].unique())
    print(f"Sample size: {len(sample_df)} track-time combinations")
    print(f"Unique times: {len(unique_times)}")
    
    # Group tracks by time
    time_to_tracks = {}
    for _, row in sample_df.iterrows():
        track_time = pd.Timestamp(row['base_time'])
        if track_time not in time_to_tracks:
            time_to_tracks[track_time] = []
        time_to_tracks[track_time].append(int(row['track_id']))
    
    start_time = time.time()
    results = []
    
    # Process one time at a time
    for track_time in unique_times:
        try:
            # Use sel with method='nearest' - most memory efficient
            mask_at_time = mask_data.sel(time=track_time, method='nearest').values
            
            # Process all tracks at this time
            for track_id in time_to_tracks[track_time]:
                cells = np.where(mask_at_time == track_id)[0]
                results.append(len(cells))
                
        except Exception as e:
            print(f"Error at time {track_time}: {e}")
            continue
    
    elapsed = time.time() - start_time
    
    print(f"Total time: {elapsed:.3f} seconds")
    print(f"Average per track-time: {elapsed/len(sample_df)*1000:.2f} ms")
    print(f"Found cells for {len([r for r in results if r > 0])} tracks")
    
    return elapsed / len(sample_df)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test track-mask matching strategies')
    parser.add_argument('--trackfile', required=True, help='Path to track file')
    parser.add_argument('--mask_file', required=True, help='Path to mask file')
    parser.add_argument('--num_samples', type=int, default=100,
                       help='Number of track-time combinations to test')
    parser.add_argument('--model_time_freq', type=str, default='3H',
                       help='Model time frequency to subsample to (e.g., 3H, 6H)')
    
    args = parser.parse_args()
    
    print("="*60)
    print("TRACK-MASK MATCHING DIAGNOSTIC TEST")
    print("="*60)
    print(f"Track file: {args.trackfile}")
    print(f"Mask file: {args.mask_file}")
    print(f"Number of samples: {args.num_samples}")
    print(f"Model time frequency: {args.model_time_freq}")
    print("="*60)
    
    # Load track file (ONLY ESSENTIAL VARIABLES!)
    print("\nLoading track file...")
    ds_tracks = xr.open_dataset(args.trackfile)
    
    # ONLY load essential variables - this is critical!
    required_vars = ['meanlon', 'meanlat', 'base_time']
    print(f"  Loading only essential variables: {required_vars}")
    subset = ds_tracks[required_vars].compute()
    df_tracks = subset.to_dataframe().reset_index()
    
    # Rename columns
    if 'tracks' in df_tracks.columns:
        df_tracks = df_tracks.rename(columns={'tracks': 'track_id'})
    if 'times' in df_tracks.columns:
        df_tracks = df_tracks.rename(columns={'times': 'time_idx'})
    
    df_tracks['base_time'] = pd.to_datetime(df_tracks['base_time'])
    
    print(f"Loaded {len(df_tracks)} track time points")
    print(f"Unique tracks: {df_tracks['track_id'].nunique()}")
    
    # IMPORTANT: Subsample to model frequency BEFORE testing
    if args.model_time_freq and args.model_time_freq not in ['1H', '1h']:
        print(f"\nSubsampling tracks to {args.model_time_freq} frequency...")
        from env_extraction_utils import subsample_tracks_by_frequency
        df_tracks = subsample_tracks_by_frequency(df_tracks, args.model_time_freq)
        print(f"After subsampling: {len(df_tracks)} track time points")
        print(f"Unique tracks: {df_tracks['track_id'].nunique()}")
    
    # Load mask file (LAZY - don't load into memory!)
    print("\nOpening mask file (lazy mode with explicit chunking)...")
    # CRITICAL: Specify chunks to prevent loading entire time coordinate
    ds_mask = xr.open_zarr(args.mask_file, chunks={'time': 1, 'cell': -1})
    
    print(f"Mask file opened successfully")
    print(f"Mask dimensions: {dict(ds_mask.dims)}")
    
    # Access mask variable (still lazy)
    mask_data = ds_mask['mcs_mask']
    # print(f"Mask variable accessed (lazy dask array)")
    # print(f"Mask dtype: {mask_data.dtype}, chunks: {mask_data.chunks}")
    
    # Get time coordinate WITHOUT loading all values
    # Just check the first time to see if conversion is needed
    print("Checking time coordinate type...")
    first_time = mask_data.time.values[0]
    
    if hasattr(first_time, 'year'):
        print("Time coordinate needs conversion from cftime")
        from env_extraction_utils import convert_time
        # Convert only when needed during processing
        needs_time_conversion = True
    else:
        print("Time coordinate is already datetime64")
        needs_time_conversion = False
    
    print("NOTE: Mask data NOT loaded into memory - using lazy dask arrays with time chunking")
    
    # Run tests
    results = {}
    
    # Test 1: Sequential streaming (slowest but minimal memory)
    results['sequential'] = test_sequential_streaming(df_tracks, mask_data, args.num_samples)
    
    # Test 2: Small batch streaming
    results['small_batch_10'] = test_small_batch_streaming(df_tracks, mask_data, args.num_samples, batch_size=10)
    results['small_batch_50'] = test_small_batch_streaming(df_tracks, mask_data, args.num_samples, batch_size=50)
    
    # Test 3: Grouped by time (optimal for our use case)
    results['grouped_by_time'] = test_grouped_by_time(df_tracks, mask_data, args.num_samples)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY - Average time per track-time (ms)")
    print("="*60)
    
    for method, avg_time in results.items():
        if avg_time is not None:
            print(f"{method:20s}: {avg_time*1000:8.2f} ms")
    
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)
    
    # Find best method
    valid_results = {k: v for k, v in results.items() if v is not None}
    if valid_results:
        best_method = min(valid_results, key=valid_results.get)
        print(f"Fastest method: {best_method}")
        print(f"Speed: {valid_results[best_method]*1000:.2f} ms per track-time")
        
        if 'grouped_by_time' in best_method:
            print("\nRecommendation: Use grouped_by_time approach")
            print("  - Load each unique time ONCE")
            print("  - Process all tracks at that time")
            print("  - Minimal memory (one time slice at a time)")
            print("  - Optimal I/O reuse")
        elif 'small_batch' in best_method:
            batch_size = best_method.split('_')[-1]
            print(f"\nRecommendation: Use small batch approach (batch_size={batch_size})")
            print(f"  - Load {batch_size} times at once")
            print("  - Process and discard")
            print("  - Balance between memory and speed")
        elif 'sequential' in best_method:
            print("\nRecommendation: Use sequential streaming")
            print("  - Minimal memory footprint")
            print("  - Slowest but most reliable")
    
    print("="*60)


if __name__ == "__main__":
    main()
