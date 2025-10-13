#!/bin/bash
#SBATCH -A m1867
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:30:00
#SBATCH -N 1
#SBATCH -J test_lf_extraction
#SBATCH -o slurm-%j.out
#SBATCH -e slurm-%j.err

# Activate environment
module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Run focused test with 500K positions (1.5M areas) - Vectorized vs Batched only
# echo "Focused test: Vectorized vs Batched with 500,000 positions (1,500,000 areas)..."
srun -n 1 -c 32 --cpu_bind=cores python test_land_fraction_extraction.py 100000
