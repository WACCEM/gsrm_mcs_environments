"""
Ultra-minimal test to verify mask data access

Based on zarr structure:
- Shape: (8760, 786432) - 8760 times × 786432 cells
- Chunks: (24, 65536) - 24 times × 65536 cells
- Compression: lz4
- Size: 55 GB uncompressed

Strategy: Use zarr directly to bypass xarray/dask overhead
"""

import zarr
import numpy as np
import pandas as pd
import xarray as xr
import sys
import time


def test_zarr_direct(mask_file):
    """Test 1: Access using zarr library directly"""
    print("TEST 1: Opening with zarr library directly...")
    store = zarr.open(mask_file, mode='r')
    print(f"  Zarr store opened")
    print(f"  Arrays: {list(store.array_keys())}")
    
    mask = store['mcs_mask']
    print(f"  Mask shape: {mask.shape}")
    print(f"  Mask dtype: {mask.dtype}")
    print(f"  Mask chunks: {mask.chunks}")
    print(f"  Compression: {mask.compressor}")
    
    return mask


def test_single_time_zarr(mask, time_idx=100):
    """Test 2: Access single time slice using zarr"""
    print(f"\nTEST 2: Reading single time slice (index {time_idx}) with zarr...")
    start = time.time()
    try:
        # Direct zarr access - should be fast
        slice_data = mask[time_idx, :]
        elapsed = time.time() - start
        print(f"  Success! Time: {elapsed:.2f}s")
        print(f"  Shape: {slice_data.shape}, dtype: {slice_data.dtype}")
        print(f"  Memory: {slice_data.nbytes / 1e6:.2f} MB")
        print(f"  Non-zero cells: {np.count_nonzero(slice_data)}")
        return True, elapsed
    except Exception as e:
        print(f"  FAILED: {e}")
        return False, 0


def test_find_track_cells_zarr(mask, track_id=1, num_times=10):
    """Test 3: Find cells for a track using zarr"""
    print(f"\nTEST 3: Finding cells for track {track_id} in first {num_times} times...")
    start = time.time()
    try:
        for i in range(num_times):
            slice_data = mask[i, :]
            cells = np.where(slice_data == track_id)[0]
            if i < 3:  # Print first few
                print(f"  Time {i}: {len(cells)} cells")
        elapsed = time.time() - start
        print(f"  Completed {num_times} time slices in {elapsed:.2f}s")
        print(f"  Average: {elapsed/num_times*1000:.1f} ms per slice")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--mask_file', required=True)
    parser.add_argument('--track_file', required=True)
    args = parser.parse_args()
    
    print("="*60)
    print("MINIMAL MASK ACCESS TEST (Using Zarr Directly)")
    print("="*60)
    print(f"Mask file: {args.mask_file}")
    print("="*60)
    
    # Test 1: Open with zarr directly
    mask = test_zarr_direct(args.mask_file)
    
    # Test 2: Single time access
    success, elapsed = test_single_time_zarr(mask, time_idx=100)
    if not success:
        print("\nFAILED at single time access - stopping here")
        sys.exit(1)
    
    # Test 3: Find track cells
    success = test_find_track_cells_zarr(mask, track_id=1, num_times=10)
    if not success:
        print("\nFAILED at finding track cells - stopping here")
        sys.exit(1)
    
    # Test 4: Test with multiple random time indices
    print("\nTEST 4: Random access pattern (100 samples)...")
    start = time.time()
    random_indices = np.random.choice(mask.shape[0], size=100, replace=False)
    
    for i, idx in enumerate(random_indices[:10]):  # Show first 10
        slice_data = mask[int(idx), :]
        non_zero = np.count_nonzero(slice_data)
        if i < 3:
            print(f"  Time index {idx}: {non_zero} non-zero cells")
    
    # Do the rest silently
    for idx in random_indices[10:]:
        slice_data = mask[int(idx), :]
    
    elapsed = time.time() - start
    print(f"  Completed 100 random accesses in {elapsed:.2f}s")
    print(f"  Average: {elapsed/100*1000:.1f} ms per slice")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)
    print("\nZarr direct access is working.")
    print(f"Performance: ~{elapsed/100*1000:.1f} ms per time slice")
    print("\nConclusion: Use zarr directly instead of xarray for mask access!")
    

if __name__ == "__main__":
    main()
