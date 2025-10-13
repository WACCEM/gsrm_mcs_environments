#!/usr/bin/env python3
"""
Test different optimization strategies for circular area calculation.
The bottleneck: 730K positions × 3 radii = 2.2M hp.query_disc() calls

Tests:
1. Sequential (current approach)
2. ThreadPoolExecutor (parallel HEALPix operations)
3. Reduced progress print frequency
4. Vectorized approach (if possible)
"""
import numpy as np
import pandas as pd
import xarray as xr
import healpy as hp
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from easygems import healpix as egh
import sys
from datetime import datetime

def convert_time(time_array):
    """Convert cftime to standard datetime64"""
    if hasattr(time_array[0], 'year'):  # It's a cftime object
        return np.array([np.datetime64(datetime(t.year, t.month, t.day, t.hour)) 
                         for t in time_array])  
                       
    return time_array

def timer(func):
    """Decorator to time function execution"""
    def wrapper(*args, **kwargs):
        start = time.time()
        print(f"\n{'='*60}")
        print(f"Testing: {func.__name__}")
        print(f"{'='*60}")
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"✓ Completed in {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        return result, elapsed
    return wrapper


@timer
def method1_sequential_current(mcs_data, hp_grid, radii, progress_freq=1000):
    """Method 1: Current sequential approach with configurable progress frequency"""
    nside = egh.get_nside(hp_grid)
    nest = True
    all_areas = {}
    total_points = len(mcs_data)
    
    print(f"  Processing {total_points} positions with progress every {progress_freq} positions...")
    
    for idx, row in mcs_data.iterrows():
        if idx % progress_freq == 0:
            print(f"  Progress: {idx}/{total_points} positions processed...")
            
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
    
    return all_areas


@timer
def method2_threadpool(mcs_data, hp_grid, radii, n_workers=4, progress_freq=1000):
    """Method 2: ThreadPoolExecutor for parallel HEALPix operations"""
    nside = egh.get_nside(hp_grid)
    nest = True
    all_areas = {}
    total_points = len(mcs_data)
    
    print(f"  Processing {total_points} positions with {n_workers} workers...")
    
    def process_position(idx, row):
        """Process one position (all radii)"""
        track_id = int(row['tracks'])
        time_idx = int(row['times'])
        cell_idx = int(row['trigger_idx'])
        
        position_areas = {}
        for radius in radii:
            area_pixels = hp.query_disc(
                nside, 
                hp.pix2vec(nside, cell_idx, nest=nest), 
                np.radians(radius),
                inclusive=False, 
                nest=nest
            )
            position_areas[(track_id, time_idx, radius)] = area_pixels
        
        return position_areas
    
    # Process with ThreadPoolExecutor
    processed_count = 0
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(process_position, idx, row): idx 
            for idx, row in mcs_data.iterrows()
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            position_areas = future.result()
            all_areas.update(position_areas)
            
            processed_count += 1
            if processed_count % progress_freq == 0:
                print(f"  Progress: {processed_count}/{total_points} positions processed...")
    
    return all_areas


@timer
def method3_threadpool_batched(mcs_data, hp_grid, radii, n_workers=4, batch_size=100, progress_freq=1000):
    """Method 3: ThreadPoolExecutor with batched processing (reduce overhead)"""
    nside = egh.get_nside(hp_grid)
    nest = True
    all_areas = {}
    total_points = len(mcs_data)
    
    print(f"  Processing {total_points} positions with {n_workers} workers (batch_size={batch_size})...")
    
    def process_batch(batch_rows):
        """Process a batch of positions"""
        batch_areas = {}
        for idx, row in batch_rows:
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
                batch_areas[(track_id, time_idx, radius)] = area_pixels
        
        return batch_areas
    
    # Create batches
    rows_list = list(mcs_data.iterrows())
    batches = [rows_list[i:i+batch_size] for i in range(0, len(rows_list), batch_size)]
    
    print(f"  Created {len(batches)} batches...")
    
    # Process batches with ThreadPoolExecutor
    processed_batches = 0
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(process_batch, batch): i for i, batch in enumerate(batches)}
        
        for future in as_completed(futures):
            batch_areas = future.result()
            all_areas.update(batch_areas)
            
            processed_batches += 1
            processed_positions = processed_batches * batch_size
            if processed_positions % progress_freq == 0:
                print(f"  Progress: {processed_positions}/{total_points} positions processed...")
    
    return all_areas


def load_test_data(n_positions=1000):
    """Load a subset of real data for testing"""
    print(f"\nLoading test data ({n_positions} positions)...")
    
    # Load catalog and dataset
    import intake
    catalog_url = "https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
    cat = intake.open_catalog(catalog_url)["NERSC"]
    ds = cat["scream_ne120"](zoom=8).to_dask().pipe(egh.attach_coords, signed_lon=True)
    ds = ds.assign_coords(time=convert_time(ds.time.values))

    # Get grid
    print("  Computing HEALPix grid...")
    hp_grid = ds[['lat', 'lon']].compute()
    nside = egh.get_nside(hp_grid)
    
    # Load track file
    trackfile = "/global/cfs/cdirs/m4581/gsharing/hackathon/tracking/mcs/scream/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
    print(f"  Loading track file...")
    mcs_trackstats = xr.open_dataset(trackfile)
    
    # Get subset
    required_vars = ['meanlon', 'meanlat', 'base_time']
    subset = mcs_trackstats[required_vars].compute()
    df = subset.to_dataframe().reset_index()
    
    # Filter
    df = df.dropna(subset=['meanlat', 'meanlon'])
    df = df[(df['meanlat'] >= -30) & (df['meanlat'] <= 30)]
    df = df[(df['base_time'] >= np.datetime64('2019-08-01')) & 
            (df['base_time'] <= np.datetime64('2020-08-31'))]
    
    # Take first n_positions
    df = df.head(n_positions).copy()
    df = df.reset_index(drop=True)
    
    # Calculate HEALPix indices
    print(f"  Calculating HEALPix indices...")
    pixel_indices = hp.ang2pix(nside, df['meanlon'].values, df['meanlat'].values, 
                               nest=True, lonlat=True)
    df['trigger_idx'] = pixel_indices
    
    print(f"  Loaded {len(df)} positions")
    return df, hp_grid


def main():
    # Configuration
    if len(sys.argv) > 1:
        n_positions = int(sys.argv[1])
    else:
        n_positions = 1000  # Default: test with 1000 positions
    
    radii = np.array([5.0, 3.5, 2.0])
    
    print("="*60)
    print("CIRCULAR AREA OPTIMIZATION TEST")
    print("="*60)
    print(f"Test size: {n_positions} positions × {len(radii)} radii = {n_positions * len(radii)} operations")
    print(f"Full dataset: 730,827 positions × {len(radii)} radii = 2,192,481 operations")
    print("="*60)
    
    # Load test data
    df, hp_grid = load_test_data(n_positions)
    
    # Store results
    results = {}
    
    # Method 1: Sequential with normal progress (every 1000)
    print("\n" + "="*60)
    print("METHOD 1: Sequential (current approach, progress every 1000)")
    print("="*60)
    areas1, time1 = method1_sequential_current(df, hp_grid, radii, progress_freq=1000)
    results['Sequential (1K progress)'] = time1
    
    # Method 1b: Sequential with less frequent progress (every 10000)
    print("\n" + "="*60)
    print("METHOD 1b: Sequential (reduced progress every 10000)")
    print("="*60)
    areas1b, time1b = method1_sequential_current(df, hp_grid, radii, progress_freq=10000)
    results['Sequential (10K progress)'] = time1b
    
    # Method 2: ThreadPool (per-position parallelism)
    print("\n" + "="*60)
    print("METHOD 2: ThreadPoolExecutor (4 workers, per-position)")
    print("="*60)
    areas2, time2 = method2_threadpool(df, hp_grid, radii, n_workers=4, progress_freq=1000)
    results['ThreadPool (4 workers)'] = time2
    
    # Method 3: ThreadPool with batching
    print("\n" + "="*60)
    print("METHOD 3: ThreadPoolExecutor (4 workers, batch_size=100)")
    print("="*60)
    areas3, time3 = method3_threadpool_batched(df, hp_grid, radii, n_workers=4, 
                                               batch_size=100, progress_freq=1000)
    results['ThreadPool (batched)'] = time3
    
    # Summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    print(f"Test size: {n_positions} positions")
    print(f"Radii: {radii}")
    print()
    
    # Sort by time
    sorted_results = sorted(results.items(), key=lambda x: x[1])
    
    baseline_time = results['Sequential (1K progress)']
    print(f"{'Method':<30} {'Time (s)':<12} {'Speedup':<10} {'Est. Full (min)':<15}")
    print("-"*70)
    
    for method, elapsed in sorted_results:
        speedup = baseline_time / elapsed
        # Estimate full dataset time
        full_time_seconds = (730827 / n_positions) * elapsed
        full_time_minutes = full_time_seconds / 60
        
        print(f"{method:<30} {elapsed:>10.2f}s  {speedup:>8.2f}x  {full_time_minutes:>13.1f} min")
    
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)
    
    best_method, best_time = sorted_results[0]
    best_full_time_min = (730827 / n_positions) * best_time / 60
    
    print(f"Best method: {best_method}")
    print(f"Estimated time for full dataset: {best_full_time_min:.1f} minutes ({best_full_time_min/60:.1f} hours)")
    
    if best_full_time_min > 30:
        print(f"\n⚠️  Still exceeds 30-minute debug queue limit!")
        print(f"   Consider:")
        print(f"   1. Submit to regular queue (longer time limit)")
        print(f"   2. Further optimize (vectorize HEALPix operations?)")
        print(f"   3. Cache circular areas to disk for reuse")
    else:
        print(f"\n✓ Should complete within 30-minute debug queue limit!")
    
    print("="*60)


if __name__ == "__main__":
    main()
