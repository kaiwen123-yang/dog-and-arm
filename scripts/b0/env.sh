#!/usr/bin/env bash
# Launch B0 with isolated Python/native search paths and optional desktop variables.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -eq 0 ]]; then
    echo 'Usage: bash scripts/b0/env.sh COMMAND [ARGUMENTS...]' >&2
    exit 2
fi
cd "$root"
prefix="$root/.conda/envs/arm-and-dog"
if [[ ! -f "$prefix/conda-meta/history" || ! -x "$prefix/bin/python" ]]; then
    echo 'Create the B0 environment with scripts/b0/setup_env.sh first.' >&2
    exit 1
fi
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH VIRTUAL_ENV
export PATH="$prefix/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export CONDA_PREFIX="$prefix" CONDA_DEFAULT_ENV=arm-and-dog PYTHONNOUSERSITE=1 PYTHONPATH="$root"
export XDG_CACHE_HOME="$root/.cache" WARP_CACHE_PATH="$root/.cache/warp"
export TORCH_HOME="$root/.cache/torch" TORCHINDUCTOR_CACHE_DIR="$root/.cache/torchinductor"
export TRITON_CACHE_DIR="$root/.cache/triton" CUDA_CACHE_PATH="$root/.cache/cuda"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
exec "$@"
