#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:10:00
#SBATCH -J compare_data
#SBATCH -A m1867
#SBATCH --mail-user=laura.paccini@pnnl.gov
#SBATCH --mail-type=FAIL,END

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

echo "Starting dataset comparison at $(date)"

srun -n 1 -c 32 --cpu_bind=cores python compare_datasets_temporal_coverage.py

echo "Comparison complete at $(date)"
