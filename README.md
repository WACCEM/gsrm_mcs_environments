# MCS Environmental Analysis for Global Storm-Resolving Models

Analysis of environmental conditions around Mesoscale Convective Systems (MCS) in global storm-resolving models (GSRMs) and reanalysis data.

**Author:** Laura Paccini  
**Last Updated:** November 2025

---

## 📁 Repository Structure

### `extract_environments/`
Scripts to extract environmental statistics around MCS tracks:
- **Model output:** HEALPix grid data (SCREAM, ICON, IFS, NICAM, UM)
- **Reanalysis:** ERA5 regular grid data
- **Methods:** Circular area extraction, mask-based extraction
- **Output:** Statistics (mean, median, std, etc.) in parquet format

**Start here:** See `extract_environments/README.md` for detailed documentation.

### `pre_process/`
Scripts to pre-compute derived variables and perform preliminary calculations:
- Wind shear calculations (deep shear, low-level shear)
- Monthly mean statistics
<!-- - Custom diagnostic variables
- Data preparation for extraction workflows -->

### `analysis/`
Jupyter notebooks for analysis and visualization:
- MCS environmental condition analysis
- Comparison across models and observations
- Statistical analysis and plotting

---

## 🚀 Quick Start

1. **Extract environmental statistics:**
   ```bash
   cd extract_environments/
   sbatch run_get_env_vars_SCREAM.sh  # or other model
   ```

2. **Pre-compute derived variables:**
   ```bash
   cd pre_process/
   # Run pre-processing scripts as needed
   ```

3. **Analyze results:**
   ```bash
   cd analysis/
   jupyter notebook
   ```

---

## 📖 Documentation

- **Extraction workflows:** `extract_environments/README.md`
- **Pre-processing:** See scripts in `pre_process/` directory
- **Analysis:** See individual notebooks in `analysis/` directory

---

## 🔗 Related Resources

- **MCS Tracking:** WACCEM MCS tracking workflows
- **Model Data:** Digital Earths Global Hackathon catalog
- **ERA5 Data:** `/global/cfs/cdirs/m1867/zfeng/gpm/mcs_global`

---

**For detailed usage and examples, see the README files in each subdirectory.**
