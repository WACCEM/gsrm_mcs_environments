#!/usr/bin/env python
"""
Test script to demonstrate ERA5 time frequency filtering and NaN skipping.

This script shows how the time frequency parameter works and how
all-NaN time steps are automatically filtered.
"""

import numpy as np
import pandas as pd

def demonstrate_time_frequency():
    """Show how time frequency filtering works."""
    
    print("="*60)
    print("ERA5 Time Frequency Filtering Demonstration")
    print("="*60)
    
    # Simulate ERA5 rel_times (hourly from -23 to 223)
    all_rel_times = np.arange(-23, 224, 1)
    
    print(f"\nOriginal ERA5 data:")
    print(f"  Total time steps: {len(all_rel_times)}")
    print(f"  Range: {all_rel_times.min()}h to {all_rel_times.max()}h")
    print(f"  First 20 values: {all_rel_times[:20]}")
    
    # Test different frequencies
    frequencies = ['1H', '3H', '6H']
    
    for freq in frequencies:
        print(f"\n" + "-"*60)
        print(f"Frequency: {freq}")
        print("-"*60)
        
        # Parse frequency
        freq_hours = int(freq.rstrip('Hh'))
        
        # Filter times
        filtered_times = all_rel_times[all_rel_times % freq_hours == 0]
        
        print(f"  Filtered time steps: {len(filtered_times)}")
        print(f"  Reduction: {(1 - len(filtered_times)/len(all_rel_times))*100:.1f}%")
        print(f"  First 20 values: {filtered_times[:20]}")
        print(f"  Pre-convective (≤0): {filtered_times[filtered_times <= 0]}")
        
        # Show what happens at track initiation (t=0)
        if 0 in filtered_times:
            idx_zero = np.where(filtered_times == 0)[0][0]
            print(f"  Around initiation (t=0): {filtered_times[max(0,idx_zero-3):idx_zero+4]}")


def demonstrate_nan_filtering():
    """Show how NaN filtering works for tracks of different durations."""
    
    print("\n\n" + "="*60)
    print("Track Duration and NaN Filtering Demonstration")
    print("="*60)
    
    # Simulate three tracks with different durations
    tracks = [
        {'id': 1, 'duration_hours': 48, 'name': 'Short track'},
        {'id': 2, 'duration_hours': 120, 'name': 'Medium track'},
        {'id': 3, 'duration_hours': 200, 'name': 'Long track'},
    ]
    
    all_rel_times = np.arange(-23, 224, 1)
    freq = '3H'
    freq_hours = int(freq.rstrip('Hh'))
    filtered_times = all_rel_times[all_rel_times % freq_hours == 0]
    
    print(f"\nUsing {freq} frequency: {len(filtered_times)} time steps")
    print(f"Time steps to check: {filtered_times[:15]}... (first 15)")
    
    for track in tracks:
        print(f"\n" + "-"*60)
        print(f"{track['name']} (ID={track['id']}, duration={track['duration_hours']}h)")
        print("-"*60)
        
        # Determine which times have data
        valid_times = filtered_times[filtered_times <= track['duration_hours']]
        nan_times = filtered_times[filtered_times > track['duration_hours']]
        
        print(f"  Valid time steps (with data): {len(valid_times)}")
        print(f"  NaN time steps (track ended): {len(nan_times)}")
        print(f"  Skipped: {len(nan_times)} time steps ({len(nan_times)*100/len(filtered_times):.1f}%)")
        
        if len(valid_times) > 0:
            print(f"  Last valid time: {valid_times[-1]}h")
        if len(nan_times) > 0:
            print(f"  First NaN time: {nan_times[0]}h")


def compare_with_model_output():
    """Compare ERA5 extraction with model output time steps."""
    
    print("\n\n" + "="*60)
    print("Comparison with Model Output")
    print("="*60)
    
    models = [
        {'name': 'SCREAM', 'freq': '3H'},
        {'name': 'UM', 'freq': '3H'},
        {'name': 'ICON', 'freq': '6H'},
    ]
    
    all_rel_times = np.arange(-23, 224, 1)
    
    for model in models:
        print(f"\n{model['name']} (model frequency: {model['freq']})")
        print("-"*60)
        
        freq_hours = int(model['freq'].rstrip('Hh'))
        era5_times = all_rel_times[all_rel_times % freq_hours == 0]
        
        print(f"  ERA5 extracted at {model['freq']}: {len(era5_times)} time steps")
        print(f"  Pre-convective steps: {len(era5_times[era5_times <= 0])}")
        print(f"  Track duration steps (example 100h track): {len(era5_times[(era5_times > 0) & (era5_times <= 100)])}")
        print(f"  Example times: {era5_times[:10]}")
    
    print("\n" + "="*60)
    print("Result: ERA5 and model output have matching time steps!")
    print("This enables direct statistical comparison.")
    print("="*60)


if __name__ == '__main__':
    demonstrate_time_frequency()
    demonstrate_nan_filtering()
    compare_with_model_output()
    
    print("\n\n" + "="*60)
    print("Fill Value Handling")
    print("="*60)
    print("\nERA5 data uses different conventions for missing data:")
    print("  - era5_2d: Uses NaN for missing values")
    print("  - era5_2d_derived: Uses -999.0 as fill value")
    print("\nThe script automatically handles both:")
    print("  - Valid data: values > -900")
    print("  - Missing data: NaN or values ≤ -900")
    print("\nExample: Track data at t=100h (after track ended)")
    print("  All values = -999.0 → Skipped (no statistics calculated)")
    print("="*60)
    
    print("\n\n" + "="*60)
    print("Summary")
    print("="*60)
    print("1. Time frequency filtering reduces computation by extracting")
    print("   only the time steps that match model output frequency")
    print("2. NaN filtering skips time steps after track has ended")
    print("3. Fill value filtering (-999.0) is applied for era5_2d_derived")
    print("4. All tracks have same pre-convective period (rel_times ≤ 0)")
    print("5. Track duration varies, but we only process valid times")
    print("6. This ensures efficient and accurate comparison with models")
    print("="*60)
