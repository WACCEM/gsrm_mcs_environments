#!/usr/bin/env python3
"""
Comprehensive test: All methods with MultiIndex O(1) lookup
Testing with larger dataset (500K positions) to match real-world performance

Tests:
1. ThreadPool (16 workers): Parallel processing + MultiIndex lookup
2. Sequential: Simple loop + MultiIndex lookup  
3. Batched (500): Batched processing + MultiIndex lookup
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
    if hasattr(time_array[0], 'year'):
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
def method1_parallel_current(all_areas, lf_data, mcs_data, n_workers=16):
    """Method 1: Parallel with ThreadPoolExecutor + MultiIndex O(1) lookup"""
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"  Processing {total_areas} areas with {n_workers} workers (MultiIndex O(1) lookup)...")
    
    def process_area(area_key):
        track_id, time_idx, radius = area_key
        pixels = all_areas[area_key]
        
        # O(1) MultiIndex lookup instead of O(n) boolean masking
        try:
            track_data = mcs_data.loc[(track_id, time_idx)]
        except KeyError:
            return None
        
        try:
            area_fraction_values = lf_data.sel(cell=pixels).values
            valid_mask = ~np.isnan(area_fraction_values)
            valid_fractions = area_fraction_values[valid_mask]
            
            if len(valid_fractions) == 0:
                return None
            
            mean_lf = float(np.mean(valid_fractions))
            
            return {
                'track_id': int(track_id),
                'time_idx': int(time_idx),
                'radius': radius,
                'mean_land_fraction': mean_lf,
                'num_pixels': len(valid_fractions),
            }
        except Exception as e:
            return None
    
    results = []
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(process_area, key): key for key in area_keys}
        
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
    
    return pd.DataFrame(results)


@timer
def method3_sequential_with_lookup(all_areas, lf_data, mcs_data):
    """Method 3: Sequential + MultiIndex O(1) lookup for track metadata"""
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"  Processing {total_areas} areas sequentially with MultiIndex lookup...")
    
    results = []
    for idx, area_key in enumerate(area_keys):
        if idx % 10000 == 0 and idx > 0:
            print(f"    Progress: {idx}/{total_areas}")
            
        track_id, time_idx, radius = area_key
        pixels = all_areas[area_key]
        
        # O(1) MultiIndex lookup for track metadata
        try:
            track_data = mcs_data.loc[(track_id, time_idx)]
        except KeyError:
            continue
        
        try:
            area_fraction_values = lf_data.sel(cell=pixels).values
            valid_mask = ~np.isnan(area_fraction_values)
            valid_fractions = area_fraction_values[valid_mask]
            
            if len(valid_fractions) == 0:
                continue
            
            mean_lf = float(np.mean(valid_fractions))
            
            results.append({
                'track_id': int(track_id),
                'time_idx': int(time_idx),
                'radius': radius,
                'mean_land_fraction': mean_lf,
                'num_pixels': len(valid_fractions),
            })
        except Exception as e:
            continue
    
    return pd.DataFrame(results)


@timer  
def method4_batched(all_areas, lf_data, mcs_data, batch_size=500):
    """Method 4: Batched processing + MultiIndex O(1) lookup"""
    area_keys = list(all_areas.keys())
    total_areas = len(area_keys)
    
    print(f"  Processing {total_areas} areas with batched approach (batch_size={batch_size}) + MultiIndex lookup...")
    
    results = []
    
    for batch_start in range(0, total_areas, batch_size):
        batch_end = min(batch_start + batch_size, total_areas)
        batch_keys = area_keys[batch_start:batch_end]
        
        if batch_start % 10000 == 0 and batch_start > 0:
            print(f"    Progress: {batch_start}/{total_areas}")
        
        for area_key in batch_keys:
            track_id, time_idx, radius = area_key
            pixels = all_areas[area_key]
            
            # O(1) MultiIndex lookup for track metadata
            try:
                track_data = mcs_data.loc[(track_id, time_idx)]
            except KeyError:
                continue
            
            try:
                area_fraction_values = lf_data.sel(cell=pixels).values
                valid_fractions = area_fraction_values[~np.isnan(area_fraction_values)]
                
                if len(valid_fractions) == 0:
                    continue
                
                mean_lf = float(np.mean(valid_fractions))
                
                results.append({
                    'track_id': int(track_id),
                    'time_idx': int(time_idx),
                    'radius': radius,
                    'mean_land_fraction': mean_lf,
                    'num_pixels': len(valid_fractions),
                })
            except Exception as e:
                continue
    
    return pd.DataFrame(results)


def load_test_data(n_positions=10000):
    """Load a subset of real data for testing - KEEP MULTIINDEX"""
    print(f"\nLoading test data ({n_positions} positions)...")
    
    # Load catalog and dataset
    import intake
    catalog_url = "https://digital-earths-global-hackathon.github.io/catalog/catalog.yaml"
    cat = intake.open_catalog(catalog_url)["NERSC"]
    ds = cat["scream_ne120"](zoom=8).to_dask().pipe(egh.attach_coords, signed_lon=True)

    # Get grid
    print("  Computing HEALPix grid...")
    hp_grid = ds[['lat', 'lon']].compute()
    nside = egh.get_nside(hp_grid)
    
    # Get land fraction data
    print("  Getting land fraction data reference...")
    land_fraction_data = ds['LANDFRAC']
    
    # Load track file
    trackfile = "/global/cfs/cdirs/m4581/gsharing/hackathon/tracking/mcs/scream/stats/mcs_tracks_final_20190801.0000_20200901.0000.nc"
    print(f"  Loading track file...")
    mcs_trackstats = xr.open_dataset(trackfile)
    
    # Get subset
    required_vars = ['meanlon', 'meanlat', 'base_time']
    print("  Computing track subset...")
    subset = mcs_trackstats[required_vars].compute()
    
    # CRITICAL: Keep MultiIndex by NOT calling reset_index()
    print("  Converting to DataFrame (keeping MultiIndex)...")
    df = subset.to_dataframe()  # Preserves (tracks, times) MultiIndex
    
    # Filter
    print("  Filtering (removing NaNs)...")
    df = df.dropna(subset=['meanlat', 'meanlon'])
    df = df[(df['meanlat'] >= -30) & (df['meanlat'] <= 30)]
    df = df[(df['base_time'] >= np.datetime64('2019-08-01')) & 
            (df['base_time'] <= np.datetime64('2020-08-31'))]
    
    # Take first n_positions
    df = df.head(n_positions).copy()
    
    print(f"  DataFrame has MultiIndex: {isinstance(df.index, pd.MultiIndex)}")
    print(f"  Index names: {df.index.names}")
    
    # Calculate HEALPix indices
    print(f"  Calculating HEALPix indices...")
    pixel_indices = hp.ang2pix(nside, df['meanlon'].values, df['meanlat'].values, 
                               nest=True, lonlat=True)
    df['trigger_idx'] = pixel_indices
    
    # Calculate circular areas (using proven sequential method)
    print(f"  Calculating circular areas...")
    radii = np.array([5.0, 3.5, 2.0])
    nest = True
    all_areas = {}
    
    for idx, row in df.iterrows():
        # idx is now a tuple (track_id, time_idx) due to MultiIndex
        track_id, time_idx = idx
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
    
    # Get all unique pixels and load land fraction data once
    print(f"  Loading land fraction for all areas...")
    all_pixels = set()
    for pixels in all_areas.values():
        all_pixels.update(pixels)
    all_pixels = list(all_pixels)
    
    lf_data = land_fraction_data.sel(cell=all_pixels).compute()
    
    print(f"  Loaded {len(df)} positions, {len(all_areas)} areas, {len(all_pixels)} unique pixels")
    print(f"  ✓ MCS data has MultiIndex: {isinstance(df.index, pd.MultiIndex)}")
    return all_areas, lf_data, df, hp_grid


def main():
    # Configuration
    if len(sys.argv) > 1:
        n_positions = int(sys.argv[1])
    else:
        n_positions = 500000  # Default: test with 500K positions (close to full 730K)
    
    print("="*60)
    print("LAND FRACTION EXTRACTION - COMPREHENSIVE TEST")
    print("="*60)
    print(f"Test size: {n_positions} positions × 3 radii = {n_positions * 3} areas")
    print(f"Full dataset: 730,827 positions × 3 radii = 2,192,481 areas")
    print()
    print("Comparing: ThreadPool vs Sequential vs Batched")
    print("All methods use MultiIndex O(1) lookup for track metadata")
    print("="*60)
    
    # Load test data
    all_areas, lf_data, df, hp_grid = load_test_data(n_positions)
    
    # Store results
    results = {}
    
    # Method 1: ThreadPool (parallel with 16 workers)
    print("\n" + "="*60)
    print("METHOD 1: ThreadPool (16 workers)")
    print("="*60)
    df1, time1 = method1_parallel_current(all_areas, lf_data, df, n_workers=16)
    results['ThreadPool (16)'] = time1
    
    # Method 2: Sequential with MultiIndex lookup
    print("\n" + "="*60)
    print("METHOD 2: Sequential + MultiIndex")
    print("="*60)
    df2, time2 = method3_sequential_with_lookup(all_areas, lf_data, df)
    results['Sequential+MultiIndex'] = time2
    
    # Method 3: Batched (batch_size=500)
    print("\n" + "="*60)
    print("METHOD 3: Batched (batch_size=500) + MultiIndex")
    print("="*60)
    df3, time3 = method4_batched(all_areas, lf_data, df, batch_size=500)
    results['Batched (500)'] = time3
    
    # Summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    print(f"Test size: {n_positions} positions × 3 radii = {len(all_areas)} areas")
    print(f"Scaling factor: {2192481 / len(all_areas):.2f}x to full dataset")
    print()
    
    # Sort by time
    sorted_results = sorted(results.items(), key=lambda x: x[1])
    
    baseline_time = sorted_results[0][1]  # Fastest method
    print(f"{'Method':<30} {'Time (s)':<12} {'Rate (areas/s)':<15} {'Est. Full (min)':<15}")
    print("-"*75)
    
    for method, elapsed in sorted_results:
        speedup = baseline_time / elapsed
        rate = len(all_areas) / elapsed
        # Estimate full dataset time
        full_time_seconds = (2192481 / len(all_areas)) * elapsed
        full_time_minutes = full_time_seconds / 60
        
        marker = "★" if method == sorted_results[0][0] else " "
        print(f"{marker} {method:<28} {elapsed:>10.2f}s  {rate:>13.0f}      {full_time_minutes:>13.1f} min")
    
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)
    
    best_method, best_time = sorted_results[0]
    best_full_time_min = (2192481 / len(all_areas)) * best_time / 60
    
    print(f"★ Best method: {best_method}")
    print(f"  Estimated time for full dataset: {best_full_time_min:.1f} minutes ({best_full_time_min/60:.2f} hours)")
    
    if best_full_time_min > 30:
        print(f"\n⚠️  May exceed 30-minute debug queue limit!")
        print(f"   Consider:")
        print(f"   1. Submit to regular queue (longer time limit)")
        print(f"   2. Process one radius at a time (~{best_full_time_min/3:.1f} min each)")
    else:
        print(f"\n✓ Should complete within 30-minute debug queue limit!")
    
    # Compare with old version performance
    print("\n" + "="*60)
    print("COMPARISON WITH OLD VERSION")
    print("="*60)
    old_version_time = 28  # minutes for 2,923,308 areas
    old_version_rate = 2923308 / (old_version_time * 60)  # areas per second
    
    best_rate = len(all_areas) / best_time  # areas per second
    
    print(f"Old version: {old_version_rate:.0f} areas/sec ({old_version_time} min for 2.9M areas)")
    print(f"Best method: {best_rate:.0f} areas/sec ({best_full_time_min:.1f} min estimated for 2.2M areas)")
    
    performance_ratio = best_rate / old_version_rate
    if performance_ratio >= 0.9:  # Within 10%
        print(f"\n✓ Performance comparable to old version! ({performance_ratio:.1%})")
    elif performance_ratio >= 1.1:
        print(f"\n✓✓ FASTER than old version! ({performance_ratio:.1%})")
    else:
        print(f"\n⚠️  Slower than old version: {performance_ratio:.1%} of old speed")
    
    print("="*60)


if __name__ == "__main__":
    main()
