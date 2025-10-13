#!/bin/bash
#SBATCH -N 1
#SBATCH -C cpu
#SBATCH -q debug
#SBATCH -t 00:20:00
#SBATCH -J test_optimization
#SBATCH -A m1867

module load python
conda activate /global/common/software/m1867/python/lp_env/easy

# Test with 10000 positions using the SAME srun configuration as main script
# This properly runs on the compute node, not login node
echo "Testing circular area calculation optimization strategies..."
echo "Running on compute node with srun (same as main script)..."
srun -n 1 -c 32 --cpu_bind=cores python test_circular_area_optimization.py 100000
