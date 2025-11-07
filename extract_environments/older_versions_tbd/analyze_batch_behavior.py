"""
Diagnostic script to analyze why batch counts don't change after resampling

This shows what's happening with the time batching after 3H resampling.
"""

import pandas as pd
import numpy as np

print("="*80)
print("UNDERSTANDING THE BATCH BEHAVIOR")
print("="*80)

# Simulate the track duration case
print("\n1. TRACK DURATION EXTRACTION:")
print("-" * 40)

# After subsampling tracks to 3H, you have 243,477 track-time points
# But these track-time points reference the ORIGINAL hourly timestamps!
num_track_points = 243477
print(f"Number of track-time points after 3H subsampling: {num_track_points}")

# The issue: unique_times collects ALL UNIQUE timestamps from the tracks
# Even though you SUBSAMPLED to 3H, the tracks still reference ~10,199 unique hourly times
# This is because:
# - Track 1 might have times: 00:00, 03:00, 06:00, ...
# - Track 2 might have times: 01:00, 04:00, 07:00, ...
# - Track 3 might have times: 02:00, 05:00, 08:00, ...
# When you collect ALL unique times across ALL tracks, you get most of the hourly times back!

unique_times_in_tracks = 10199  # From your log: "Loading hur data for 173007 pixels and 10199 time steps"
print(f"Unique times referenced by tracks: {unique_times_in_tracks}")
print(f"  → This is the UNION of all track timestamps")
print(f"  → Even though each track is subsampled to 3H, different tracks have different offsets")
print(f"  → So the union covers most hourly times!")

# Time batching calculation
time_batch_1000 = (unique_times_in_tracks + 999) // 1000
time_batch_500 = (unique_times_in_tracks + 499) // 500

print(f"\nTime batching with time_batch_size=1000: {time_batch_1000} batches")
print(f"Time batching with time_batch_size=500: {time_batch_500} batches")

# But here's the KEY: The dataset is already resampled to 3H!
# So when you request 10,199 hourly times with method='nearest', 
# xarray finds the nearest 3H time for each request
# Result: Only 3,401 unique times are actually loaded
actual_times_loaded = 3401
print(f"\nActual times loaded from resampled dataset: {actual_times_loaded}")
print(f"  → xarray method='nearest' maps multiple requests to same 3H times")
print(f"  → This is why you see: '10199 requested → 3401 actual times'")

print("\n" + "="*80)
print("2. PRE-CONVECTIVE DATA EXTRACTION:")
print("-" * 40)

num_tracks = 32327
hours_before = 24
model_freq_hours = 3
num_preconv_times_per_track = hours_before // model_freq_hours  # 24 / 3 = 8

print(f"Number of tracks: {num_tracks}")
print(f"Pre-convective period: {hours_before} hours before initiation")
print(f"Model frequency: {model_freq_hours}H")
print(f"Pre-convective times per track: {num_preconv_times_per_track}")

# Similar issue: Collect all pre-convective times across all tracks
# Different tracks start at different hours, so union is large
unique_preconv_times = 10214  # From your log: "Loading pre-convective data: 161672 pixels × 10214 times"
print(f"\nUnique pre-convective times across all tracks: {unique_preconv_times}")
print(f"  → This is ~14 months × 24 hours = ~10,224 hours")
print(f"  → Each track needs 8 times, but union of all tracks covers most hours")

# More pixels for pre-convective (includes all radii for first position)
num_preconv_pixels = 161672  # From log
num_duration_pixels = 173007  # From log

print(f"\nPixels for pre-convective: {num_preconv_pixels}")
print(f"Pixels for track duration: {num_duration_pixels}")
print(f"  → Pre-convective uses first position only, but all radii")
print(f"  → Duration uses all positions along track")

# Time batching for pre-convective
time_batch_preconv_1000 = (unique_preconv_times + 999) // 1000
time_batch_preconv_500 = (unique_preconv_times + 499) // 500

print(f"\nPre-convective time batching with time_batch_size=1000: {time_batch_preconv_1000} batches")
print(f"Pre-convective time batching with time_batch_size=500: {time_batch_preconv_500} batches")

# Data volume per batch
bytes_per_float32 = 4
mb_per_batch_1000 = (num_preconv_pixels * 1000 * bytes_per_float32) / (1024**2)
mb_per_batch_500 = (num_preconv_pixels * 500 * bytes_per_float32) / (1024**2)

print(f"\nData volume per batch:")
print(f"  time_batch_size=1000: {num_preconv_pixels} × 1000 × 4 bytes = {mb_per_batch_1000:.1f} MB")
print(f"  time_batch_size=500: {num_preconv_pixels} × 500 × 4 bytes = {mb_per_batch_500:.1f} MB")

print("\n" + "="*80)
print("3. WHY DOES time_batch_size=1000 SEEM FASTER?")
print("-" * 40)

print("\nPossible reasons:")
print("  1. FEWER REQUESTS: 11 batches vs 21 batches")
print("     → Each request has overhead (network, auth, catalog lookup)")
print("     → Fewer requests = less total overhead")
print()
print("  2. SERVER EFFICIENCY: Larger requests may be more efficient")
print("     → Server can optimize for larger sequential reads")
print("     → Less context switching between requests")
print()
print("  3. NO 502 ERRORS: After 3H resampling, even 1000-time batches work")
print("     → 617 MB per batch is below the server's rejection threshold")
print("     → You're not hitting the timeout anymore")
print()
print("  4. PRE-CONVECTIVE BOTTLENECK: This is the slow part")
print("     → More pixels than duration (161,672 vs 173,007)")
print("     → More unique times (10,214 vs 10,199)")
print("     → Processing ~161,672 × 8 = 1.3M area extractions")

print("\n" + "="*80)
print("4. THE REAL ISSUE: WHY NO BENEFIT FROM 3H RESAMPLING?")
print("-" * 40)

print("\nExpected: Resampling 1H → 3H should reduce unique times by ~3×")
print(f"Reality: Still requesting {unique_times_in_tracks} times (similar to original)")
print()
print("Root cause: TRACK SUBSAMPLING HAPPENS, BUT TIME COLLECTION DOESN'T BENEFIT")
print()
print("Here's what happens:")
print("  1. Tracks are subsampled to 3H → fewer track-time points (65% reduction)")
print("  2. But each track keeps its ORIGINAL timestamps (not aligned to dataset times)")
print("  3. When collecting unique times across ALL tracks, the union is still large")
print("  4. Different tracks have different start times → different 3H offsets")
print("     Example:")
print("       Track A starts 2020-01-01 00:00 → times: 00:00, 03:00, 06:00, ...")
print("       Track B starts 2020-01-01 01:00 → times: 01:00, 04:00, 07:00, ...")
print("       Track C starts 2020-01-01 02:00 → times: 02:00, 05:00, 08:00, ...")
print("     Union of A+B+C covers HOURLY times!")
print()
print("  5. When you request these times with method='nearest' from 3H dataset:")
print("     → xarray maps them to nearest 3H times")
print("     → This reduces 10,199 requests → 3,401 actual times loaded")
print("     → But you still need to MAKE 10,199 requests!")

print("\n" + "="*80)
print("5. SOLUTION: ALIGN TRACK TIMES TO DATASET TIMES")
print("-" * 40)

print("\nInstead of subsampling tracks and keeping original timestamps:")
print("  1. Load dataset times: [2020-01-01 00:00, 2020-01-01 03:00, ...]")
print("  2. For each track position, find NEAREST dataset time")
print("  3. Replace track timestamp with dataset timestamp")
print("  4. NOW unique_times will be ~3,401 instead of ~10,199")
print()
print("This would:")
print("  ✓ Reduce time batches: 11 → 4 (with time_batch_size=1000)")
print("  ✓ Reduce requests to server by ~3×")
print("  ✓ Speed up both duration and pre-convective extraction")
print("  ✓ Actually benefit from the 3H resampling")

print("\n" + "="*80)
print("6. WHY IS PRE-CONVECTIVE SLOWER?")
print("-" * 40)

print("\nComparing track duration vs pre-convective:")
print()
print("Track duration:")
print(f"  - Pixels: {num_duration_pixels}")
print(f"  - Times requested: {unique_times_in_tracks}")
print(f"  - Times loaded: {actual_times_loaded}")
print(f"  - Areas to process: 730,431")
print(f"  - Batch size: 500 areas")
print(f"  - Estimated processing: 730,431 / 500 = 1,461 area batches")
print()
print("Pre-convective:")
print(f"  - Pixels: {num_preconv_pixels} (slightly fewer)")
print(f"  - Times requested: {unique_preconv_times} (slightly more)")
print(f"  - Processing: 32,327 tracks × 8 times/track × 3 radii = ~775,848 extractions")
print()
print("So pre-convective has:")
print("  - Similar data volume to load")
print("  - Similar number of extractions to process")
print("  - BUT more time batches with time_batch_size=500 (21 vs 21)")
print()
print("The slowness is likely:")
print("  1. Sequential processing of 21 time batches (no parallelization)")
print("  2. Each batch requires server request + compute()")
print("  3. Processing nested loops: tracks × times × radii")
print("  4. 30-minute time limit is tight for this workload")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print()
print("Keep time_batch_size=1000 for IFS:")
print("  ✓ Faster (fewer requests)")
print("  ✓ No 502 errors after 3H resampling")
print("  ✓ 11 batches instead of 21")
print()
print("If still hitting time limit, consider:")
print("  1. Request longer time allocation (1-2 hours)")
print("  2. Process fewer tracks per job (split by date ranges)")
print("  3. Implement time alignment (as described above)")
print()
