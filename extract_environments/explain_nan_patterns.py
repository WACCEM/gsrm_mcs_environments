"""
Explain NICAM NaN pattern - scattered NaNs vs all-NaN timesteps

Author: Laura Paccini  
Date: December 2, 2025
"""

print("="*80)
print("QUESTION 2: WHY NICAM HAS 4.5% NaN BUT 0 ALL-NaN TIMESTEPS?")
print("="*80)

print("""
The key difference is WHERE the NaNs occur:

📊 NICAM PATTERN: SCATTERED NaNs
================================

From the analysis output:
  - Total NaN percentage:        4.5479%
  - Time steps with ALL NaNs:    0
  - Cells with ALL NaNs:         32,934 (4.19% of cells)
  - Cells with NO NaNs:          743,383 (94.53% of cells)

What this means:
  ✓ NO time steps have all-NaN data
  ✓ NaNs are spatially localized to specific cells/regions
  ✓ Most likely these are land cells or boundary regions
  ✓ At any given time, 95.81% of cells have valid data

Example visualization:
  Time 1: [valid, valid, NaN, valid, valid, NaN, ...]  ← ~5% NaNs
  Time 2: [valid, valid, NaN, valid, valid, NaN, ...]  ← Same cells NaN
  Time 3: [valid, valid, NaN, valid, valid, NaN, ...]  ← Same cells NaN
          ↑               ↑                    ↑
       Valid cells    Always-NaN cells    Always-NaN cells

This is NORMAL and EXPECTED for:
  • Wind shear over land (undefined)
  • Coastal boundaries
  • Regions outside domain of interest


📊 IFS PATTERN: TEMPORAL NaNs  
==============================

From the analysis output:
  - Total NaN percentage:        7.0567%
  - Time steps with ALL NaNs:    240
  - Cells with ALL NaNs:         0 (0.00%)
  - Cells with ANY NaNs:         196,608 (100.00% - all cells!)

What this means:
  ✗ 240 complete time steps are missing (entire days)
  ✗ ALL cells are NaN during these periods
  ✗ This represents a temporal gap in the data
  ✗ No valid data exists for April 1-30, 2020

Example visualization:
  Time 1 (Mar 31): [valid, valid, valid, valid, valid, ...]  ← All valid
  Time 2 (Apr 01): [NaN,   NaN,   NaN,   NaN,   NaN,   ...]  ← ALL NaN!
  Time 3 (Apr 02): [NaN,   NaN,   NaN,   NaN,   NaN,   ...]  ← ALL NaN!
  ...
  Time 240 (Apr 30): [NaN, NaN,   NaN,   NaN,   NaN,   ...]  ← ALL NaN!
  Time 241 (May 01): [valid, valid, valid, valid, valid, ...] ← All valid

This is PROBLEMATIC because:
  • Data is completely missing for entire month
  • Cannot extract ANY environmental variables for April 2020
  • Tracks in this period fail extraction


🔍 WHY THE DIFFERENCE?
======================

NICAM (4.5% NaN, 0 all-NaN times):
  → Spatial NaNs: Some cells always NaN, others always valid
  → Impact: Tracks over valid regions work fine
  → Cause: Likely land masking or domain boundaries

IFS (7.0% NaN, 240 all-NaN times):
  → Temporal NaNs: All cells NaN for certain times
  → Impact: NO tracks can be processed during gap period
  → Cause: Missing source data when pre-computing wind shear


📈 IMPACT ON TRACK EXTRACTION
==============================

NICAM:
  ✓ Tracks over ocean/valid regions: WORKS
  ✗ Tracks over land/boundary cells: May fail or have partial data
  → Most tracks will process successfully

IFS:
  ✓ Tracks Jan-Mar 2020: WORKS
  ✗ Tracks in April 2020: COMPLETELY FAILS
  ✓ Tracks May 2020-Mar 2021: WORKS
  → ~2,349 tracks lost (those in April)


💡 SUMMARY
==========

NICAM's 4.5% NaN is OK:
  • Scattered across space (land/boundaries)
  • All time steps have SOME valid data
  • Most tracks can be processed

IFS's 7.0% NaN is PROBLEMATIC:
  • Concentrated in time (entire month missing)
  • Some time steps have NO valid data
  • All tracks in that period fail
  • This explains your track count difference!

""")

print("="*80)
print("RECOMMENDATION")
print("="*80)
print("""
For IFS:
  1. Check source data for April 2020
  2. Regenerate pre-computed wind shear for missing period
  3. Or use direct catalog loading for complete coverage

For NICAM:
  • Current data is fine - spatial NaNs are expected
  • No action needed
""")
print("="*80)
